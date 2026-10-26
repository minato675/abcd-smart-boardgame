"""Audio boundaries: locks, canonical device resolution, and callback-only capture."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable, Protocol

from .contracts import AudioBlock


class AudioError(RuntimeError):
    pass


class ResourceBusyError(AudioError):
    pass


@dataclass(frozen=True, slots=True)
class CanonicalDevice:
    identity: str
    index: int | None
    name: str
    host_api: str
    max_input_channels: int
    default_sample_rate: float


@dataclass(slots=True)
class AudioMetrics:
    callback_count: int = 0
    callback_overflow_count: int = 0
    callback_duration_ns: int = 0
    dropped_blocks: int = 0
    dropped_samples: int = 0
    discontinuities: int = 0


class AudioSource(Protocol):
    def start(self, generation: int, sink: Callable[[AudioBlock], bool]) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


def _canonical_lock_digest(identity: str) -> str:
    encoded = f"{len(identity.encode('utf-8'))}:{identity}".encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ExclusiveResourceLocks:
    """Hold independent room and physical-device advisory locks for a process."""

    def __init__(self, root: str | Path, room_number: str, device_identity: str) -> None:
        self.root = Path(root)
        self.room_number = room_number
        self.device_identity = device_identity
        self._handles: list[Any] = []

    def acquire(self) -> None:
        if self._handles:
            raise AudioError("resource locks are already held")
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AudioError("cannot create the configured lock root") from exc
        identities = (
            ("room", self.room_number),
            ("device", self.device_identity),
        )
        try:
            import fcntl

            for kind, identity in identities:
                path = self.root / f"{kind}-{_canonical_lock_digest(identity)}.lock"
                handle = path.open("a+")
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    handle.close()
                    raise ResourceBusyError(f"{kind} lock is already held") from exc
                self._handles.append(handle)
        except Exception:
            self.release()
            raise

    def release(self) -> None:
        try:
            import fcntl
        except ImportError:
            fcntl = None
        while self._handles:
            handle = self._handles.pop()
            if fcntl is not None:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
            try:
                handle.close()
            except OSError:
                pass

    def __enter__(self) -> "ExclusiveResourceLocks":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


def resolve_sounddevice(device: Any = "default", *, sounddevice_module: Any | None = None) -> CanonicalDevice:
    try:
        sd = sounddevice_module
        if sd is None:
            import sounddevice as sd  # type: ignore[no-redef]
        info = sd.query_devices(device, "input")
        hostapis = getattr(sd, "query_hostapis", lambda: [])()
    except Exception as exc:
        raise AudioError("cannot enumerate the configured input device") from exc
    if not isinstance(info, dict):
        raise AudioError("audio backend returned invalid device information")
    host_api_index = info.get("hostapi")
    host_api = "unknown"
    if isinstance(hostapis, list) and isinstance(host_api_index, int) and 0 <= host_api_index < len(hostapis):
        host_api = str(hostapis[host_api_index].get("name", host_api_index))
    index = info.get("index", device if isinstance(device, int) else None)
    name = str(info.get("name", ""))
    if not name or int(info.get("max_input_channels", 0)) < 1:
        raise AudioError("configured device has no input channels")
    identity = f"{host_api}\x00{name}\x00{info.get('max_input_channels')}\x00{info.get('default_samplerate')}"
    return CanonicalDevice(
        identity=identity,
        index=index if isinstance(index, int) else None,
        name=name,
        host_api=host_api,
        max_input_channels=int(info.get("max_input_channels", 0)),
        default_sample_rate=float(info.get("default_samplerate", 0.0)),
    )


class SoundDeviceAudioSource:
    """RawInputStream adapter whose callback only copies and enqueues bytes."""

    def __init__(
        self,
        *,
        device: Any,
        sample_rate_hz: int = 16000,
        channels: int = 1,
        max_callback_samples: int = 4096,
        sink: Callable[[AudioBlock], bool] | None = None,
        on_discontinuity: Callable[[str, int], None] | None = None,
        sounddevice_module: Any | None = None,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.device_selector = device
        self.sample_rate_hz = sample_rate_hz
        self.channels = channels
        self.max_callback_samples = max_callback_samples
        self.sink = sink
        self.on_discontinuity = on_discontinuity
        self.sounddevice_module = sounddevice_module
        self.monotonic_ns = monotonic_ns
        self.metrics = AudioMetrics()
        self._stream: Any | None = None
        self._generation: int | None = None
        self._sample_index = 0
        self._lock = threading.Lock()
        self.canonical_device: CanonicalDevice | None = None

    def probe(self) -> CanonicalDevice:
        device = resolve_sounddevice(self.device_selector, sounddevice_module=self.sounddevice_module)
        sd = self.sounddevice_module
        if sd is None:
            try:
                import sounddevice as sd  # type: ignore[no-redef]
            except ImportError as exc:
                raise AudioError("sounddevice is not installed") from exc
        try:
            sd.check_input_settings(
                device=device.index,
                samplerate=self.sample_rate_hz,
                channels=self.channels,
                dtype="int16",
            )
        except Exception as exc:
            raise AudioError("device cannot provide 16 kHz mono PCM16 input") from exc
        self.canonical_device = device
        return device

    def start(self, generation: int, sink: Callable[[AudioBlock], bool] | None = None) -> None:
        if self._stream is not None:
            raise AudioError("audio stream is already running")
        if self.canonical_device is None:
            self.probe()
        sd = self.sounddevice_module
        if sd is None:
            try:
                import sounddevice as sd  # type: ignore[no-redef]
            except ImportError as exc:
                raise AudioError("sounddevice is not installed") from exc
        self.sink = sink or self.sink
        if self.sink is None:
            raise AudioError("audio source has no bounded sink")
        self._generation = generation
        self._sample_index = 0
        try:
            self._stream = sd.RawInputStream(
                samplerate=self.sample_rate_hz,
                blocksize=0,
                device=self.canonical_device.index if self.canonical_device else self.device_selector,
                channels=self.channels,
                dtype="int16",
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            raise AudioError("cannot open the locked input stream") from exc

    def _notify_gap(self, reason: str, samples: int) -> None:
        self.metrics.discontinuities += 1
        if self.on_discontinuity is not None:
            self.on_discontinuity(reason, samples)

    def _callback(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        started = self.monotonic_ns()
        self.metrics.callback_count += 1
        status_text = str(status) if status else ""
        if status_text and any(token in status_text.lower() for token in ("overflow", "underflow", "input")):
            self.metrics.callback_overflow_count += 1
            self._notify_gap("portaudio_status", int(frames))
        sample_count = int(frames)
        if sample_count <= 0:
            return
        if sample_count > self.max_callback_samples:
            self.metrics.dropped_blocks += 1
            self.metrics.dropped_samples += sample_count
            self._sample_index += sample_count
            self._notify_gap("oversized_callback", sample_count)
            return
        pcm_bytes = bytes(indata)
        if len(pcm_bytes) != sample_count * self.channels * 2 or self.channels != 1:
            self._sample_index += sample_count
            self._notify_gap("format_change", sample_count)
            return
        adc_time = None
        if isinstance(time_info, dict):
            value = time_info.get("inputBufferAdcTime")
            adc_time = float(value) if isinstance(value, (int, float)) else None
        else:
            value = getattr(time_info, "inputBufferAdcTime", None)
            adc_time = float(value) if isinstance(value, (int, float)) else None
        first_index = self._sample_index
        self._sample_index += sample_count
        try:
            block = AudioBlock(
                generation=self._generation if self._generation is not None else 0,
                first_sample_index=first_index,
                callback_monotonic_ns=started,
                adc_time_seconds=adc_time,
                pcm_bytes=pcm_bytes,
            )
        except ValueError:
            self._notify_gap("invalid_pcm", sample_count)
            return
        try:
            accepted = bool(self.sink(block)) if self.sink is not None else False
        except Exception:
            accepted = False
        if not accepted:
            self.metrics.dropped_blocks += 1
            self.metrics.dropped_samples += sample_count
            self._notify_gap("audio_queue_full", sample_count)
        self.metrics.callback_duration_ns += self.monotonic_ns() - started

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()
        self._generation = None

    def close(self) -> None:
        self.stop()


class FakeAudioSource:
    """Deterministic source for unit/system tests; it never touches hardware."""

    def __init__(self) -> None:
        self.generation: int | None = None
        self.sink: Callable[[AudioBlock], bool] | None = None
        self.running = False

    def start(self, generation: int, sink: Callable[[AudioBlock], bool]) -> None:
        self.generation = generation
        self.sink = sink
        self.running = True

    def push(self, pcm_bytes: bytes, *, first_sample_index: int, callback_monotonic_ns: int, adc_time_seconds: float | None = None) -> bool:
        if not self.running or self.sink is None or self.generation is None:
            return False
        return self.sink(AudioBlock(self.generation, first_sample_index, callback_monotonic_ns, adc_time_seconds, pcm_bytes))

    def stop(self) -> None:
        self.running = False
        self.sink = None
        self.generation = None

    def close(self) -> None:
        self.stop()
