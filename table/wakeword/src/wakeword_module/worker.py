"""Inference worker: the sole owner of feature buffers, model, VAD, and detector."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import math
import queue
import threading
import time
from typing import Callable, Any

from .contracts import AudioBlock, RawScores, WakeWordCandidate
from .detector import DetectionStateMachine
from .engine import OpenWakeWordEngine
from .framing import FrameDiscontinuity, PcmFrameAssembler


@dataclass(frozen=True, slots=True)
class ControlReservation:
    token: int
    generation: int


@dataclass(frozen=True, slots=True)
class ResetAndWarm:
    generation: int


@dataclass(frozen=True, slots=True)
class EnableDecisions:
    generation: int


@dataclass(frozen=True, slots=True)
class StopGeneration:
    generation: int


@dataclass(frozen=True, slots=True)
class Shutdown:
    pass


@dataclass(frozen=True, slots=True)
class EngineReady:
    generation: int


@dataclass(frozen=True, slots=True)
class WorkerScores:
    raw: RawScores
    pcm_rms: float | None = None
    pcm_peak: int | None = None
    pcm_mean: float | None = None


@dataclass(frozen=True, slots=True)
class WorkerCandidate:
    candidate: WakeWordCandidate


@dataclass(frozen=True, slots=True)
class WorkerDiscontinuity:
    generation: int
    reason: str


@dataclass(frozen=True, slots=True)
class WorkerError:
    generation: int
    component: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class WorkerStopped:
    generation: int


WorkerEvent = EngineReady | WorkerScores | WorkerCandidate | WorkerDiscontinuity | WorkerError | WorkerStopped
WorkerControl = ResetAndWarm | EnableDecisions | StopGeneration | Shutdown


class InferenceWorker:
    """A bounded, priority-controlled worker around one stateful engine."""

    def __init__(
        self,
        engine: OpenWakeWordEngine,
        detector: DetectionStateMachine,
        *,
        warmup_frames: int = 25,
        queue_blocks: int = 8,
        max_frame_age_ms: int = 160,
        event_sink: Callable[[WorkerEvent], None] | None = None,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if queue_blocks < 1:
            raise ValueError("queue_blocks must be positive")
        self.engine = engine
        self.detector = detector
        self.warmup_frames = max(25, warmup_frames)
        self.max_frame_age_ms = max_frame_age_ms
        self.event_sink = event_sink
        self.logger = logging.getLogger("wakeword_module")
        self.monotonic_ns = monotonic_ns
        self.wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self.audio_queue: queue.Queue[AudioBlock] = queue.Queue(maxsize=queue_blocks)
        self.control_queue: queue.Queue[tuple[WorkerControl, ControlReservation | None]] = queue.Queue(maxsize=max(2, queue_blocks))
        self._event_queue: queue.Queue[WorkerEvent] = queue.Queue(maxsize=max(32, queue_blocks * 4))
        self._reservation_lock = threading.Lock()
        self._reserved_controls = 0
        self._reservation_token = 0
        self._reservations: set[int] = set()
        self._generation = 0
        self._decisions_enabled = False
        self._assembler = PcmFrameAssembler(generation=0)
        self._thread: threading.Thread | None = None
        self._stop_requested = threading.Event()
        self._discontinuity_pending = False
        self._discontinuity_reason = "audio_queue_full"
        self.event_overflowed = False
        self._discontinuity_lock = threading.Lock()
        self._stream_utc_anchor: datetime | None = None
        self._stream_sample_anchor = 0
        self._held_audio: AudioBlock | None = None

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def decisions_enabled(self) -> bool:
        return self._decisions_enabled

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_requested.clear()
        self._thread = threading.Thread(target=self._run, name="wakeword-inference", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        reservation = self.reserve_terminal_control(self._generation)
        if reservation is not None:
            self.submit_control(Shutdown(), reservation=reservation)
        else:
            # Shutdown is the one bounded emergency path: never leave a
            # daemon thread running merely because a full control queue made
            # the normal command unavailable.
            self._stop_requested.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None

    def reserve_terminal_control(self, generation: int) -> ControlReservation | None:
        with self._reservation_lock:
            if self.control_queue.qsize() + self._reserved_controls >= self.control_queue.maxsize:
                return None
            self._reservation_token += 1
            token = self._reservation_token
            self._reserved_controls += 1
            self._reservations.add(token)
            return ControlReservation(token, generation)

    def submit_control(self, command: WorkerControl, reservation: ControlReservation | None = None) -> bool:
        with self._reservation_lock:
            if reservation is not None:
                if reservation.token not in self._reservations:
                    return False
                self._reservations.remove(reservation.token)
                self._reserved_controls -= 1
            elif self.control_queue.full():
                return False
            try:
                self.control_queue.put_nowait((command, reservation))
            except queue.Full:
                if reservation is not None:
                    self._reserved_controls += 1
                    self._reservations.add(reservation.token)
                return False
        return True

    def offer_audio(self, block: AudioBlock) -> bool:
        try:
            self.audio_queue.put_nowait(block)
            return True
        except queue.Full:
            self.request_discontinuity("audio_queue_full")
            return False

    def request_discontinuity(self, reason: str) -> None:
        """Callback-safe marker; the worker performs the reset later."""
        with self._discontinuity_lock:
            self._discontinuity_pending = True
            self._discontinuity_reason = reason

    def poll_events(self, max_items: int | None = None) -> list[WorkerEvent]:
        events: list[WorkerEvent] = []
        limit = max_items if max_items is not None else self._event_queue.maxsize
        for _ in range(limit):
            try:
                events.append(self._event_queue.get_nowait())
            except queue.Empty:
                break
        return events

    def _emit(self, event: WorkerEvent) -> None:
        try:
            self._event_queue.put_nowait(event)
        except queue.Full:
            # A lost lifecycle/error event is itself a fault, but never block
            # the model/audio worker to log or publish it.
            self.event_overflowed = True
            self._stop_requested.set()
        if self.event_sink is not None:
            try:
                self.event_sink(event)
            except Exception:
                pass

    def _reset_stream(self, generation: int) -> None:
        self._generation = generation
        self._decisions_enabled = False
        self._assembler.reset(generation=generation)
        self.detector.reset(generation)
        self._stream_utc_anchor = None
        self._stream_sample_anchor = 0
        self._drain_audio(generation=None)
        self._held_audio = None
        with self._discontinuity_lock:
            self._discontinuity_pending = False

    def _drain_audio(self, generation: int | None) -> None:
        retained: list[AudioBlock] = []
        while True:
            try:
                block = self.audio_queue.get_nowait()
            except queue.Empty:
                break
            if generation is None or block.generation == generation:
                continue
            retained.append(block)
        for block in retained:
            try:
                self.audio_queue.put_nowait(block)
            except queue.Full:
                break

    def _handle_control(self, command: WorkerControl) -> bool:
        if isinstance(command, Shutdown):
            self._stop_requested.set()
            self._decisions_enabled = False
            self._assembler.reset(generation=None)
            self._drain_audio(None)
            self._emit(WorkerStopped(self._generation))
            return False
        if isinstance(command, ResetAndWarm):
            try:
                self._reset_stream(command.generation)
                self.engine.reset_and_warm(self.warmup_frames)
                # The stream/sample UTC anchor begins at the first accepted
                # capture block, after warm-up, not when model warm-up ended.
                self._stream_utc_anchor = None
                self._emit(EngineReady(command.generation))
            except Exception as exc:
                self._emit(WorkerError(command.generation, "warmup", type(exc).__name__, "engine warm-up failed"))
            return True
        if isinstance(command, EnableDecisions):
            if command.generation == self._generation:
                self._decisions_enabled = True
            return True
        if isinstance(command, StopGeneration):
            if command.generation == self._generation:
                self._decisions_enabled = False
                self._assembler.reset(generation=command.generation)
                self.detector.reset(command.generation)
                self._held_audio = None
                self._drain_audio(command.generation)
                try:
                    self.engine.reset()
                except Exception as exc:
                    self._emit(WorkerError(command.generation, "reset", type(exc).__name__, "engine reset failed"))
                self._emit(WorkerStopped(command.generation))
            return True
        return True

    def _handle_discontinuity(self, reason: str) -> None:
        self._decisions_enabled = False
        self._assembler.reset(generation=self._generation)
        self.detector.reset(self._generation)
        self._stream_utc_anchor = None
        try:
            # Feature history, classifier history, optional VAD state, and the
            # library's five-frame initialization suppression all restart on a
            # discontinuity.  No queued frame can cross the gap.
            self.engine.reset_and_warm(self.warmup_frames)
        except Exception as exc:
            self._emit(WorkerError(self._generation, "recovery_warmup", type(exc).__name__, "discontinuity warm-up failed"))
            return
        self._emit(WorkerDiscontinuity(self._generation, reason))

    def _handle_audio(self, block: AudioBlock) -> None:
        if block.generation != self._generation:
            return
        if not self._decisions_enabled:
            # A callback block arriving between EngineReady and the control
            # queue's EnableDecisions command must wait without advancing any
            # feature/model state.  Keep at most one such block; overflow is a
            # discontinuity, never silently stale inference.
            if self._held_audio is None:
                self._held_audio = block
            else:
                with self._discontinuity_lock:
                    self._discontinuity_pending = True
            return
        with self._discontinuity_lock:
            if self._discontinuity_pending:
                self._discontinuity_pending = False
                reason = self._discontinuity_reason
                self._handle_discontinuity(reason)
                return
        if self._stream_utc_anchor is None:
            self._stream_utc_anchor = self.wall_clock().astimezone(timezone.utc)
            self._stream_sample_anchor = block.first_sample_index
        try:
            frames = self._assembler.append(block)
        except FrameDiscontinuity:
            self._handle_discontinuity("sample_clock_gap")
            return
        for frame in frames:
            age_ms = (self.monotonic_ns() - frame.frame_end_monotonic_ns) / 1_000_000
            if age_ms > self.max_frame_age_ms:
                self._handle_discontinuity("stale_frame")
                return
            try:
                prediction = self.engine.predict(frame.pcm)
                assert self._stream_utc_anchor is not None
                occurred = self._stream_utc_anchor + timedelta(
                    seconds=(frame.end_sample_index - self._stream_sample_anchor) / 16000
                )
                raw = RawScores(
                    generation=frame.generation,
                    sequence=frame.sequence,
                    frame_end_sample_index=frame.end_sample_index,
                    frame_end_monotonic_ns=frame.frame_end_monotonic_ns,
                    scores=prediction.scores,
                    vad_score=prediction.vad_score,
                    occurred_at_utc=occurred,
                    timestamp_uncertainty_ms=max(1.0, age_ms),
                )
                pcm_rms = pcm_peak = pcm_mean = None
                if self.logger.isEnabledFor(logging.DEBUG):
                    pcm_float = frame.pcm.astype("float32")
                    pcm_rms = math.sqrt(max(0.0, float((pcm_float * pcm_float).mean())))
                    pcm_peak = int(abs(frame.pcm.astype("int32")).max())
                    pcm_mean = float(pcm_float.mean())
                self._emit(WorkerScores(raw, pcm_rms, pcm_peak, pcm_mean))
                candidate = self.detector.feed(raw, listening=self._decisions_enabled)
                if candidate is not None:
                    self._decisions_enabled = False
                    self._emit(WorkerCandidate(candidate))
                    return
            except Exception as exc:
                self._decisions_enabled = False
                self._emit(WorkerError(self._generation, "inference", type(exc).__name__, "inference failed"))
                return

    def _run(self) -> None:
        while not self._stop_requested.is_set():
            command_item: tuple[WorkerControl, ControlReservation | None] | None = None
            try:
                command_item = self.control_queue.get_nowait()
            except queue.Empty:
                pass
            if command_item is not None:
                if not self._handle_control(command_item[0]):
                    break
                continue
            with self._discontinuity_lock:
                pending_reason = self._discontinuity_reason if self._discontinuity_pending else None
                if pending_reason is not None and self._decisions_enabled:
                    self._discontinuity_pending = False
            if pending_reason is not None and self._decisions_enabled:
                self._handle_discontinuity(pending_reason)
                continue
            if self._held_audio is not None and self._decisions_enabled:
                block = self._held_audio
                self._held_audio = None
            elif not self._decisions_enabled and self._held_audio is not None:
                # Keep the one held block until a control message enables or
                # resets the generation; do not drain more callback audio.
                time.sleep(0.005)
                continue
            else:
                try:
                    block = self.audio_queue.get(timeout=0.05)
                except queue.Empty:
                    continue
            self._handle_audio(block)
