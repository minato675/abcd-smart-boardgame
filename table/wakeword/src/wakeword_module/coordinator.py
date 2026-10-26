"""Serialized lifecycle coordinator for legacy and v2 wake-word control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any, Callable
from uuid import UUID, uuid4

from .audio import AudioSource
from .config import WakeWordConfig
from .contracts import (
    ContractError,
    InternalState,
    V2Command,
    WakeWordCandidate,
    legacy_status_payload,
    parse_legacy_command,
    parse_v2_ack,
    parse_v2_command,
    serialize_v2_status,
)
from .mqtt import CommandMessage, DurableOutboxDispatcher, MemoryPublisher, Publication, Publisher, WakeTopics
from .store import DurableStateStore, StoreError
from .worker import (
    EnableDecisions,
    EngineReady,
    InferenceWorker,
    StopGeneration,
    ResetAndWarm,
    WorkerCandidate,
    WorkerDiscontinuity,
    WorkerError,
    WorkerEvent,
    WorkerScores,
)


@dataclass(frozen=True, slots=True)
class HealthState:
    live: bool
    ready: bool
    state: str
    broker_connected: bool
    audio_active: bool
    model_quality: str
    reason: str | None = None


class WakeWordModule:
    """The only component allowed to mutate lifecycle state.

    MQTT callbacks and audio callbacks call bounded queue methods elsewhere;
    this class is normally driven by one coordinator loop via
    :meth:`process_pending`.  ``handle_message`` is synchronous for deterministic
    contract tests and still performs no model calls from the MQTT callback.
    """

    def __init__(
        self,
        config: WakeWordConfig,
        *,
        worker: InferenceWorker,
        audio_source: AudioSource,
        publisher: Publisher | None = None,
        store: DurableStateStore | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        utc_clock: Callable[[], datetime] | None = None,
        logger: logging.Logger | None = None,
        model_quality: str | None = None,
    ) -> None:
        self.config = config
        self.worker = worker
        self.audio_source = audio_source
        self.publisher: Publisher = publisher or MemoryPublisher()
        self.topics = WakeTopics(config.room_number)
        self.store = store
        if config.mqtt.contract_version == "v2" and self.store is None:
            self.store = DurableStateStore(
                config.runtime.state_store_path,
                device_id=config.device_id,
                max_rows=config.runtime.outbox_max_rows,
                max_bytes=config.runtime.outbox_max_bytes,
                reserved_rows=config.runtime.outbox_reserved_rows,
                reserved_bytes=config.runtime.outbox_reserved_bytes,
                controller_epoch=config.runtime.controller_epoch,
            )
        self.outbox_dispatcher = (
            DurableOutboxDispatcher(
                self.store,
                self.publisher,
                self.topics.status,
                publish_ack_timeout_seconds=config.mqtt.publish_ack_timeout_seconds,
            )
            if config.mqtt.contract_version == "v2" and self.store is not None
            else None
        )
        self.monotonic = monotonic
        self.utc_clock = utc_clock or (lambda: datetime.now(timezone.utc))
        self.logger = logger or logging.getLogger("wakeword_module")
        self._model_quality = model_quality or ("unverified" if config.allow_unverified_models else "verified")
        self.state = InternalState.STARTING
        self.ready = False
        self.broker_connected = False
        self.generation = 0
        self.listen_session_id: UUID | None = None
        self._pending_start: V2Command | None = None
        self._last_wire_status = "idle"
        self._latched_candidate: WakeWordCandidate | None = None
        self._running = False
        self._shutdown_requested = False
        self.metrics: dict[str, int] = {
            "invalid_command": 0,
            "retained_command": 0,
            "candidate_total": 0,
            "detection_total": 0,
            "collision_total": 0,
            "recovery_total": 0,
        }

    @property
    def audio_active(self) -> bool:
        return self.state in {InternalState.ARMING_START, InternalState.RECOVERING_AUDIO, InternalState.LISTENING}

    @property
    def health(self) -> HealthState:
        return HealthState(
            live=self._running,
            ready=self.ready,
            state=self.state.value,
            broker_connected=self.broker_connected,
            audio_active=self.audio_active,
            model_quality=self._model_quality,
            reason=None if self.state != InternalState.FAULT else "fault",
        )

    def start(self, *, broker_connected: bool = True, ready: bool = True) -> None:
        if self._running:
            return
        if self.config.mqtt.contract_version == "v2" and self.store is not None:
            self.store.open()
            # A crash can leave a non-latched session marked active.  Capture
            # is never resumed implicitly on process restart; close that
            # session before accepting a fresh, globally single-use ID.
            self.store.close_active_sessions()
            latch = self.store.restore_latch()
            if latch is not None:
                self.listen_session_id = latch.listen_session_id
                self._last_wire_status = latch.status
                self.state = InternalState.LATCHED_CALL if latch.status == "call" else InternalState.LATCHED_FINISH
            else:
                self.state = InternalState.IDLE
            # A process crash cannot leave a v2 PROCESSING command without a
            # durable terminal response.  Close it before readiness and before
            # accepting a new command; the exact rejection bytes are cached for
            # correlated retries after restart.
            for command in self.store.processing_commands():
                self._queue_v2_status(
                    status="idle",
                    listen_session_id=None,
                    command_id=command.command_id,
                    outcome="rejected",
                    reason_code="interrupted",
                    finish_command_id=command.command_id,
                    finish_state="rejected",
                    finish_reason_code="interrupted",
                )
        else:
            self.state = InternalState.IDLE
        self.worker.start()
        self._running = True
        self._shutdown_requested = False
        self.broker_connected = broker_connected
        self.ready = bool(ready and broker_connected)
        if self.ready:
            self._publish_current_status()

    def set_broker_connected(self, connected: bool) -> None:
        """Apply broker loss/recovery on the coordinator thread."""

        self.broker_connected = connected
        if not connected:
            self.ready = False
            if self.state in {InternalState.ARMING_START, InternalState.LISTENING, InternalState.RECOVERING_AUDIO}:
                if self.state == InternalState.ARMING_START:
                    self._interrupt_pending_start("interrupted")
                old_generation = self.generation
                self.generation += 1
                try:
                    self.audio_source.stop()
                finally:
                    self._submit_stop(old_generation)
                if self.config.mqtt.contract_version == "v2" and self.store is not None and self.listen_session_id is not None:
                    self.store.mark_session_closed(self.listen_session_id)
                self.state = InternalState.PAUSED_DISCONNECTED
                self._pending_start = None
            return
        if self.state == InternalState.PAUSED_DISCONNECTED:
            self.state = InternalState.IDLE
            self._last_wire_status = "idle"
        self.ready = self._running
        if self.ready:
            if self.outbox_dispatcher is not None:
                self.outbox_dispatcher.on_reconnect()
            self._publish_current_status()

    def process_pending(self, *, max_events: int = 64) -> int:
        """Drain worker events; call this from the one coordinator loop."""

        processed = 0
        for event in self.worker.poll_events(max_events):
            processed += 1
            self._handle_worker_event(event)
        if getattr(self.worker, "event_overflowed", False) and self.state != InternalState.FAULT:
            self.ready = False
            self._set_state(InternalState.FAULT, "worker_event_queue_overflow")
        if self.outbox_dispatcher is not None and self.broker_connected:
            processed += self.outbox_dispatcher.dispatch()
        return processed

    def _log_transition(self, old: InternalState, new: InternalState, reason: str) -> None:
        self.logger.info(
            "wakeword_state_transition",
            extra={"old_state": old.value, "new_state": new.value, "reason": reason},
        )

    def _set_state(self, new_state: InternalState, reason: str) -> None:
        old = self.state
        self.state = new_state
        if old != new_state:
            self._log_transition(old, new_state, reason)

    def _submit_stop(self, generation: int) -> None:
        reservation = self.worker.reserve_terminal_control(generation)
        if reservation is not None:
            self.worker.submit_control(StopGeneration(generation), reservation=reservation)

    def _publish(self, status: str, payload: bytes | None = None) -> bool:
        if payload is None:
            payload = legacy_status_payload(status)
        return self.publisher.offer(Publication(self.topics.status, payload, qos=1, retain=False, logical_key=status))

    def _publish_current_status(self) -> None:
        if self.config.mqtt.contract_version == "legacy":
            self._publish(self._last_wire_status)
        elif self.store is not None:
            latch = self.store.restore_latch()
            if latch is None and (
                self.state == InternalState.IDLE or not self.store.pending_outbox(limit=1)
            ):
                self._queue_v2_snapshot()
            elif latch is not None and latch.application_acked:
                self._queue_v2_snapshot()
            if self.outbox_dispatcher is not None:
                self.outbox_dispatcher.dispatch()

    def _offer_payload(self, payload: bytes, logical_key: str | None = None) -> bool:
        return self.publisher.offer(Publication(self.topics.status, payload, qos=1, retain=False, logical_key=logical_key))

    def _v2_status_dict(
        self,
        *,
        status: str,
        revision: int,
        listen_session_id: UUID | None,
        event_id: UUID | None = None,
        occurred_at: datetime | None = None,
        model_id: str | None = None,
        model_sha256: str | None = None,
        confidence: float | None = None,
        command_id: UUID | None = None,
        request_id: UUID | None = None,
        outcome: str | None = None,
        reason_code: str | None = None,
    ) -> dict[str, Any]:
        if status in {"call", "finish"} and listen_session_id is None:
            raise ContractError("latched v2 status requires a session")
        timestamp = (occurred_at or self.utc_clock()).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        value = {
            "contractVersion": 2,
            "deviceId": self.config.device_id,
            "statusRevision": revision,
            "status": status,
            "listenSessionId": str(listen_session_id) if listen_session_id else None,
            "eventId": str(event_id) if event_id else None,
            "occurredAt": timestamp,
            "modelId": model_id,
            "modelSha256": model_sha256,
            "confidence": confidence,
            "configRevision": self.config.config_revision,
            "commandId": str(command_id) if command_id else None,
            "requestId": str(request_id) if request_id else None,
            "outcome": outcome,
            "reasonCode": reason_code,
        }
        return value

    def _queue_v2_status(
        self,
        *,
        status: str,
        listen_session_id: UUID | None,
        event_id: UUID | None = None,
        occurred_at: datetime | None = None,
        model_id: str | None = None,
        model_sha256: str | None = None,
        confidence: float | None = None,
        command_id: UUID | None = None,
        request_id: UUID | None = None,
        outcome: str | None = None,
        reason_code: str | None = None,
        kind: str = "status",
        event_requires_ack: bool = False,
        finish_command_id: UUID | None = None,
        finish_request_id: UUID | None = None,
        finish_state: str = "accepted",
        finish_reason_code: str | None = None,
    ) -> tuple[int, bytes]:
        if self.store is None:
            raise StoreError("v2 status requires a durable store")

        def make_payload(revision: int) -> bytes:
            return serialize_v2_status(
                self._v2_status_dict(
                    status=status,
                    revision=revision,
                    listen_session_id=listen_session_id,
                    event_id=event_id,
                    occurred_at=occurred_at,
                    model_id=model_id,
                    model_sha256=model_sha256,
                    confidence=confidence,
                    command_id=command_id,
                    request_id=request_id,
                    outcome=outcome,
                    reason_code=reason_code,
                )
            )

        if finish_command_id is not None and finish_request_id is not None:
            raise ValueError("a v2 response cannot finish both a command and a request")
        item = None
        if finish_command_id is not None:
            revision, payload = self.store.finish_command_with_status(
                finish_command_id,
                payload=make_payload,
                state=finish_state,
                reason_code=finish_reason_code,
                kind=kind,
            )
        elif finish_request_id is not None:
            revision, payload = self.store.finish_request_with_status(
                finish_request_id,
                payload=make_payload,
                state=finish_state,
                reason_code=finish_reason_code,
                kind=kind,
            )
        else:
            revision = self.store.queue_status(make_payload, kind=kind, event_id=event_id, requires_ack=event_requires_ack)
            # The store has the exact payload; retrieve it by revision so the
            # publisher and restart path cannot diverge.
            item = next((item for item in self.store.pending_outbox(limit=128) if item.status_revision == revision), None)
            payload = item.payload if item is not None else make_payload(revision)
        if item is None:
            item = next((item for item in self.store.pending_outbox(limit=128) if item.status_revision == revision), None)
        # The durable dispatcher is the single publisher boundary for v2.
        # Publishing the row directly and then dispatching it would race the
        # in-flight/PUBACK bookkeeping and duplicate status or detection rows.
        if self.outbox_dispatcher is not None:
            self.outbox_dispatcher.dispatch()
        else:
            self._offer_payload(payload, logical_key=f"outbox:{item.outbox_id}" if item is not None else None)
        return revision, payload

    def _queue_v2_snapshot(
        self,
        request_id: UUID | None = None,
        *,
        command_id: UUID | None = None,
        outcome: str | None = None,
        reason_code: str | None = None,
        finish_command_id: UUID | None = None,
        finish_request_id: UUID | None = None,
        finish_state: str = "accepted",
        finish_reason_code: str | None = None,
    ) -> tuple[int, bytes]:
        latch = self.store.restore_latch() if self.store else None
        if latch is not None:
            status = latch.status
            session = latch.listen_session_id
            event_id = latch.event_id
            occurred = datetime.fromisoformat(latch.occurred_at.replace("Z", "+00:00"))
            model_id = latch.model_id
            model_sha256 = latch.model_sha256
            confidence = latch.confidence
        else:
            status = self._last_wire_status if self._last_wire_status in {"idle", "listening"} else "idle"
            session = self.listen_session_id if status == "listening" else None
            event_id = model_id = model_sha256 = None
            occurred = None
            confidence = None
        if outcome is None and request_id is not None:
            outcome = "snapshot"
        return self._queue_v2_status(
            status=status,
            listen_session_id=session,
            event_id=event_id,
            occurred_at=occurred,
            model_id=model_id,
            model_sha256=model_sha256,
            confidence=confidence,
            command_id=command_id,
            request_id=request_id,
            outcome=outcome,
            reason_code=reason_code,
            finish_command_id=finish_command_id,
            finish_request_id=finish_request_id,
            finish_state=finish_state if finish_command_id is not None else ("accepted" if outcome != "rejected" else "rejected"),
            finish_reason_code=finish_reason_code if finish_command_id is not None else reason_code,
        )

    def _handle_worker_event(self, event: WorkerEvent) -> None:
        if isinstance(event, EngineReady):
            self.logger.debug("worker_engine_ready", extra={"generation": event.generation})
            self._on_engine_ready(event)
        elif isinstance(event, WorkerScores):
            raw = event.raw
            self.logger.debug(
                "inference_scores",
                extra={
                    "generation": raw.generation,
                    "sequence": raw.sequence,
                    "frame_end_sample_index": raw.frame_end_sample_index,
                    "ssafiya_score": raw.scores.get("ssafiya"),
                    "nae_teon_kkeutnasseo_score": raw.scores.get("nae_teon_kkeutnasseo"),
                    "vad_score": raw.vad_score,
                    "pcm_rms": event.pcm_rms,
                    "pcm_peak": event.pcm_peak,
                    "pcm_mean": event.pcm_mean,
                },
            )
        elif isinstance(event, WorkerCandidate):
            self.logger.info(
                "wakeword_candidate",
                extra={
                    "generation": event.candidate.generation,
                    "frame_end_sample_index": event.candidate.frame_end_sample_index,
                    "model_id": event.candidate.model_id,
                    "score": event.candidate.raw_score,
                    "threshold": event.candidate.threshold,
                },
            )
            self._on_candidate(event.candidate)
        elif isinstance(event, WorkerDiscontinuity):
            self.logger.warning(
                "audio_discontinuity",
                extra={"generation": event.generation, "reason": event.reason},
            )
            self._on_discontinuity(event)
        elif isinstance(event, WorkerError):
            self.logger.error(
                "worker_error",
                extra={
                    "generation": event.generation,
                    "component": event.component,
                    "error_type": event.error_type,
                    "reason": event.message,
                },
            )
            self._on_worker_error(event)

    def _on_engine_ready(self, event: EngineReady) -> None:
        if event.generation != self.generation or self.state not in {InternalState.ARMING_START, InternalState.RECOVERING_AUDIO}:
            return
        recovering = self.state == InternalState.RECOVERING_AUDIO
        try:
            self.audio_source.start(event.generation, self.worker.offer_audio)
            enable_reservation = self.worker.reserve_terminal_control(event.generation)
            if enable_reservation is None:
                raise RuntimeError("worker control capacity unavailable")
            if not recovering:
                if self.config.mqtt.contract_version == "legacy":
                    self._last_wire_status = "listening"
                    if not self._publish("listening"):
                        raise RuntimeError("legacy publisher queue is full")
                else:
                    command = self._pending_start
                    if command is None:
                        self._queue_v2_snapshot()
                    else:
                        revision, response = self._queue_v2_status(
                            status="listening",
                            listen_session_id=self.listen_session_id,
                            command_id=command.command_id,
                            outcome="accepted",
                            finish_command_id=command.command_id,
                            finish_state="accepted",
                        )
                    self._last_wire_status = "listening"
            else:
                if self.config.mqtt.contract_version == "legacy":
                    self._last_wire_status = "listening"
                    self._publish("listening")
                else:
                    self._queue_v2_snapshot()
            if not self.worker.submit_control(EnableDecisions(event.generation), reservation=enable_reservation):
                raise RuntimeError("cannot enable worker decisions")
            self._pending_start = None
            self._set_state(InternalState.LISTENING, "engine_ready")
        except Exception as exc:
            self._fail_active_start("capture_or_enable_failure", exc)

    def _fail_active_start(self, reason: str, error: Exception | None = None) -> None:
        self._interrupt_pending_start("interrupted")
        old_generation = self.generation
        self.generation += 1
        try:
            self.audio_source.stop()
        finally:
            self._submit_stop(old_generation)
        self.ready = False
        self._set_state(InternalState.FAULT, reason)
        if self.config.mqtt.contract_version == "legacy" and self.broker_connected:
            self._last_wire_status = "idle"
            self._publish("idle")

    def _interrupt_pending_start(self, reason: str = "interrupted") -> None:
        pending_start = self._pending_start
        if pending_start is None:
            return
        if pending_start.command_id is not None and self.config.mqtt.contract_version == "v2" and self.store is not None:
            try:
                self._queue_v2_status(
                    status="idle",
                    listen_session_id=None,
                    command_id=pending_start.command_id,
                    outcome="rejected",
                    reason_code=reason,
                    finish_command_id=pending_start.command_id,
                    finish_state="rejected",
                    finish_reason_code=reason,
                )
            except Exception:
                self.ready = False
            try:
                if pending_start.listen_session_id is not None:
                    self.store.mark_session_closed(pending_start.listen_session_id)
            except Exception:
                self.ready = False
        self._pending_start = None

    def _on_discontinuity(self, event: WorkerDiscontinuity) -> None:
        if event.generation != self.generation or self.state != InternalState.LISTENING:
            return
        self.metrics["recovery_total"] += 1
        self._set_state(InternalState.RECOVERING_AUDIO, event.reason)
        old_generation = self.generation
        self.generation += 1
        try:
            # The worker has already invalidated its model state.  Stop the
            # old PortAudio stream before EngineReady attempts to open the
            # replacement generation; RawInputStream cannot be started twice.
            self.audio_source.stop()
        except Exception:
            self._submit_stop(old_generation)
            self.ready = False
            self._set_state(InternalState.FAULT, "recovery_capture_stop_failure")
            return
        self._submit_stop(old_generation)
        reservation = self.worker.reserve_terminal_control(self.generation)
        if reservation is None or not self.worker.submit_control(ResetAndWarm(self.generation), reservation=reservation):
            self._fail_active_start("recovery_control_capacity")

    def _on_worker_error(self, event: WorkerError) -> None:
        if event.generation != self.generation:
            return
        self._fail_active_start(event.component)

    def _on_candidate(self, candidate: WakeWordCandidate) -> None:
        if candidate.generation != self.generation or self.state != InternalState.LISTENING:
            return
        self.metrics["candidate_total"] += 1
        old_generation = self.generation
        self.generation += 1
        try:
            self.audio_source.stop()
        finally:
            self._submit_stop(old_generation)
        event_id = uuid4()
        self.listen_session_id = self.listen_session_id or uuid4()
        self._latched_candidate = candidate
        self._last_wire_status = candidate.wire_status
        model = self.config.model_by_id[candidate.model_id]
        occurred = candidate.occurred_at_utc
        if self.config.mqtt.contract_version == "v2" and self.store is not None:
            try:
                revision, payload = self.store.commit_detection(
                    status=candidate.wire_status,
                    event_id=event_id,
                    listen_session_id=self.listen_session_id,
                    model_id=candidate.model_id,
                    model_sha256=model.sha256,
                    confidence=candidate.raw_score,
                    occurred_at=occurred.isoformat().replace("+00:00", "Z"),
                    config_revision=self.config.config_revision,
                    payload=lambda revision: serialize_v2_status(
                        self._v2_status_dict(
                            status=candidate.wire_status,
                            revision=revision,
                            listen_session_id=self.listen_session_id,
                            event_id=event_id,
                            occurred_at=occurred,
                            model_id=candidate.model_id,
                            model_sha256=model.sha256,
                            confidence=candidate.raw_score,
                        )
                    ),
                )
                item = next((item for item in self.store.pending_outbox(limit=128) if item.status_revision == revision), None)
                if self.outbox_dispatcher is not None:
                    self.outbox_dispatcher.dispatch()
                else:
                    self._offer_payload(item.payload if item else payload, logical_key=f"outbox:{item.outbox_id}" if item else None)
                self.store.mark_session_closed(self.listen_session_id)
            except Exception:
                self._set_state(InternalState.FAULT, "detection_store_failure")
                self.ready = False
                return
        else:
            if not self._publish(candidate.wire_status):
                self._set_state(InternalState.FAULT, "detection_publish_failure")
                self.ready = False
                return
        self.metrics["detection_total"] += 1
        if self.config.continue_listening_after_detection:
            self._latched_candidate = None
            self._set_state(InternalState.RECOVERING_AUDIO, "accepted_detection_rearm")
            reservation = self.worker.reserve_terminal_control(self.generation)
            if reservation is None or not self.worker.submit_control(
                ResetAndWarm(self.generation), reservation=reservation
            ):
                self._fail_active_start("detection_rearm_control_capacity")
            return
        self._set_state(InternalState.LATCHED_CALL if candidate.wire_status == "call" else InternalState.LATCHED_FINISH, "accepted_detection")

    def _start_session(self, command: V2Command | None = None) -> bool:
        if not self.ready or self.state not in {InternalState.IDLE, InternalState.LATCHED_CALL, InternalState.LATCHED_FINISH}:
            return False
        if command is not None and self.store is not None and not self.store.reserve_start_quota():
            self._v2_reject(command, "invalid_state")
            return False
        if command is None and self.store is not None and self.store.restore_latch() is not None:
            self.store.clear_latch()
        self.generation += 1
        self.listen_session_id = command.listen_session_id if command is not None else uuid4()
        self._pending_start = command
        self._set_state(InternalState.ARMING_START, "accepted_start")
        reservation = self.worker.reserve_terminal_control(self.generation)
        if reservation is None:
            self._fail_active_start("worker_control_capacity")
            return False
        if not self.worker.submit_control(ResetAndWarm(self.generation), reservation=reservation):
            self._fail_active_start("worker_control_capacity")
            return False
        return True

    def _stop_session(self, command: V2Command | None = None) -> None:
        self._interrupt_pending_start("interrupted")
        old_generation = self.generation
        self.generation += 1
        try:
            self.audio_source.stop()
        finally:
            self._submit_stop(old_generation)
        if self.store is not None and self.config.mqtt.contract_version == "v2":
            if self.listen_session_id is not None:
                self.store.mark_session_closed(self.listen_session_id)
            self.store.clear_latch()
        self.listen_session_id = None
        self._pending_start = None
        self._latched_candidate = None
        self._last_wire_status = "idle"
        self._set_state(InternalState.IDLE, "accepted_stop")
        if self.config.mqtt.contract_version == "legacy":
            self._publish("idle")
        elif command is not None:
            self._queue_v2_status(
                status="idle",
                listen_session_id=None,
                command_id=command.command_id,
                outcome="accepted",
                finish_command_id=command.command_id,
                finish_state="accepted",
            )
        else:
            self._queue_v2_snapshot()

    def _handle_legacy(self, kind: str) -> None:
        if kind == "request-status":
            if self.broker_connected:
                self._publish(self._last_wire_status)
            return
        if kind == "start":
            if self.state in {InternalState.IDLE, InternalState.LATCHED_CALL, InternalState.LATCHED_FINISH}:
                self._start_session()
            elif self.state == InternalState.LISTENING:
                self._publish("listening")
            elif self.state == InternalState.FAULT and self.broker_connected:
                self._last_wire_status = "idle"
                self._publish("idle")
            return
        if kind == "stop":
            if self.state == InternalState.FAULT:
                if self.broker_connected:
                    self._last_wire_status = "idle"
                    self._publish("idle")
            else:
                self._stop_session()

    def _publish_cached(self, payload: bytes) -> None:
        self._offer_payload(payload)

    def _v2_existing(self, command: V2Command) -> bool:
        if self.store is None:
            return False
        existing = self.store.get_command(command.identity_id)
        if existing is None:
            return False
        if existing.kind != command.kind or existing.digest != command.digest:
            self._v2_reject(command, "id_conflict", persist=False)
        elif existing.response is not None:
            self._publish_cached(existing.response)
        else:
            self._queue_v2_snapshot(command_id=command.command_id, outcome="in_progress")
        return True

    def _v2_reject(
        self,
        command: V2Command,
        reason: str,
        *,
        persist: bool = True,
        close_session_id: UUID | None = None,
    ) -> None:
        if self.store is None:
            return
        if not persist:
            self._queue_v2_snapshot(
                command_id=command.command_id,
                outcome="rejected",
                reason_code=reason,
            )
            return
        if persist and command.command_id is not None:
            if self.store.get_command(command.command_id) is None:
                self.store.begin_command(
                    command_id=command.command_id,
                    kind=command.kind,
                    digest=command.digest,
                    controller_epoch=command.controller_epoch or self.config.runtime.controller_epoch or uuid4(),
                    command_sequence=command.command_sequence or 0,
                    listen_session_id=command.listen_session_id or uuid4(),
                )
            revision, response = self._queue_v2_snapshot(
                command_id=command.command_id,
                outcome="rejected",
                reason_code=reason,
                finish_command_id=command.command_id,
                finish_state="rejected",
                finish_reason_code=reason,
            )
            if close_session_id is not None:
                self.store.mark_session_closed(close_session_id)

    def _handle_v2(self, command: V2Command) -> None:
        if self.store is None:
            return
        now = self.utc_clock().astimezone(timezone.utc)
        if command.issued_at > now + timedelta(seconds=self.config.runtime.clock_skew_seconds):
            self._v2_reject(command, "future_issued_at")
            return
        if now - command.issued_at > timedelta(seconds=self.config.runtime.max_command_age_seconds):
            self._v2_reject(command, "expired")
            return
        if self._v2_existing(command):
            return
        if command.kind in {"start", "stop"}:
            assert command.command_id and command.controller_epoch is not None and command.command_sequence is not None and command.listen_session_id is not None
            reason = self.store.accept_sequence(controller_epoch=command.controller_epoch, command_sequence=command.command_sequence, command_id=command.command_id)
            if reason is not None:
                self._v2_reject(command, reason)
                return
            session_state_before = self.store.session_state(command.listen_session_id)
            self.store.begin_command(
                command_id=command.command_id,
                kind=command.kind,
                digest=command.digest,
                controller_epoch=command.controller_epoch,
                command_sequence=command.command_sequence,
                listen_session_id=command.listen_session_id,
            )
            close_on_reject = command.listen_session_id if session_state_before is None else None
            if command.kind == "start" and session_state_before is not None and not (
                self.state == InternalState.LISTENING and command.listen_session_id == self.listen_session_id
            ):
                self._v2_reject(command, "session_reuse")
                return
            pending_latch = self.store.restore_latch()
            if pending_latch is not None and not pending_latch.application_acked:
                self._v2_reject(command, "event_unacknowledged", close_session_id=close_on_reject)
                return
            if not self.ready:
                self._v2_reject(command, "invalid_state", close_session_id=close_on_reject)
                return
            if command.kind == "start":
                if self.state in {InternalState.IDLE, InternalState.LATCHED_CALL, InternalState.LATCHED_FINISH}:
                    self._start_session(command)
                elif self.state == InternalState.LISTENING and command.listen_session_id == self.listen_session_id:
                    self._queue_v2_status(
                        status="listening",
                        listen_session_id=self.listen_session_id,
                        command_id=command.command_id,
                        outcome="duplicate",
                        finish_command_id=command.command_id,
                        finish_state="duplicate",
                    )
                else:
                    self._v2_reject(command, "invalid_state", close_session_id=close_on_reject)
            else:
                stale_closed = session_state_before == "closed"
                latch = self.store.restore_latch()
                allow_acknowledged_latch_stop = latch is not None and latch.listen_session_id == command.listen_session_id and latch.application_acked
                session_matches = self.listen_session_id is not None and command.listen_session_id == self.listen_session_id
                if (not allow_acknowledged_latch_stop) and (
                    stale_closed or session_state_before is None or not session_matches
                ):
                    self._v2_reject(command, "stale_session", close_session_id=close_on_reject)
                else:
                    self._stop_session(command)
            return
        assert command.request_id is not None
        existing = self.store.begin_request(request_id=command.request_id, digest=command.digest)
        if existing is not None:
            if existing.digest != command.digest:
                # Request IDs are never overwritten; correlate the conflict.
                self._queue_v2_snapshot(command.request_id, outcome="rejected", reason_code="id_conflict")
            elif existing.response is not None:
                self._publish_cached(existing.response)
            else:
                self._queue_v2_snapshot(command.request_id)
            return
        self._queue_v2_snapshot(command.request_id, finish_request_id=command.request_id)

    def handle_message(self, message: CommandMessage) -> None:
        if message.retained:
            self.metrics["retained_command"] += 1
            return
        topic_to_kind = {
            self.topics.start_listen: "start",
            self.topics.stop_listen: "stop",
            self.topics.request_status: "request-status",
            self.topics.ack: "ack",
        }
        kind = topic_to_kind.get(message.topic)
        if kind is None:
            return
        try:
            if kind == "ack":
                if self.config.mqtt.contract_version != "v2":
                    return
                ack = parse_v2_ack(message.payload)
                if self.store is not None:
                    ack_id = UUID(ack["ackId"])
                    event_id = UUID(ack["eventId"])
                    latch = self.store.restore_latch()
                    if latch is not None and latch.event_id == event_id and latch.listen_session_id == UUID(ack["listenSessionId"]):
                        self.store.record_application_ack(
                            ack_id=ack_id,
                            event_id=event_id,
                            listen_session_id=latch.listen_session_id,
                            received_at=ack["receivedAt"],
                        )
                return
            if self.config.mqtt.contract_version == "legacy":
                parse_legacy_command(message.payload)
                self._handle_legacy(kind)
            else:
                self._handle_v2(parse_v2_command(kind, message.payload))
        except (ContractError, ValueError, StoreError):
            self.metrics["invalid_command"] += 1

    def shutdown(self, deadline_seconds: float = 5.0) -> None:
        self._shutdown_requested = True
        self._set_state(InternalState.SHUTTING_DOWN, "shutdown")
        self._interrupt_pending_start("interrupted")
        if self.config.mqtt.contract_version == "v2" and self.store is not None and self.listen_session_id is not None and self.store.restore_latch() is None:
            self.store.mark_session_closed(self.listen_session_id)
        try:
            self.audio_source.stop()
        finally:
            self.worker.stop(timeout=deadline_seconds)
        if self.config.mqtt.contract_version == "legacy" and self.broker_connected:
            self._last_wire_status = "idle"
            self._publish("idle")
        elif self.config.mqtt.contract_version == "v2" and self.store is not None and self.store.restore_latch() is None and self.broker_connected:
            self._last_wire_status = "idle"
            self.listen_session_id = None
            self._queue_v2_snapshot()
        if self.store is not None:
            self.store.close()
        self.ready = False
        self.broker_connected = False
        self._running = False
