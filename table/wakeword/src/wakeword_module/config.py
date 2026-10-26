"""Strict typed configuration for the wake-word service."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import os
from pathlib import Path
import re
from typing import Any, Literal
from uuid import UUID

import yaml

from .contracts import MODEL_IDS, WIRE_STATUSES, canonical_json


class ConfigError(ValueError):
    pass


def _keys(value: Any, allowed: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a mapping")
    unknown = set(value) - allowed
    if unknown:
        raise ConfigError(f"{where} has unknown keys: {', '.join(sorted(unknown))}")
    return value


def _required(value: dict[str, Any], name: str, where: str) -> Any:
    if name not in value:
        raise ConfigError(f"{where}.{name} is required")
    return value[name]


def _int(value: Any, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    return value


def _float(value: Any, name: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ConfigError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise ConfigError(f"{name} must be <= {maximum}")
    return result


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{name} must be boolean")
    return value


def _text(value: Any, name: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and value == ""):
        raise ConfigError(f"{name} must be a {'non-empty ' if nonempty else ''}string")
    return value


@dataclass(frozen=True, slots=True)
class ModelPolicy:
    id: str
    phrase: str
    wire_status: Literal["call", "finish"]
    path: Path
    sha256: str
    trigger_threshold: float
    evidence_window_frames: int
    required_hits: int
    vad_mode: Literal["off", "observe", "gate"]
    vad_threshold: float | None = None
    vad_context_oldest_lag_frames: int | None = None
    vad_context_newest_lag_frames: int | None = None
    vad_aggregate: Literal["max", "mean"] | None = None

    def __post_init__(self) -> None:
        if self.id not in MODEL_IDS:
            raise ConfigError(f"unsupported model id: {self.id}")
        if self.wire_status not in {"call", "finish"}:
            raise ConfigError(f"invalid wire status for {self.id}")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ConfigError(f"{self.id}.sha256 must be a lowercase SHA-256 digest")
        if not 0 < self.trigger_threshold < 1:
            raise ConfigError(f"{self.id}.trigger_threshold must be between 0 and 1")
        if self.evidence_window_frames < 1:
            raise ConfigError(f"{self.id}.evidence_window_frames must be >= 1")
        if not 1 <= self.required_hits <= self.evidence_window_frames:
            raise ConfigError(f"{self.id}.required_hits must be within the evidence window")
        if self.vad_mode not in {"off", "observe", "gate"}:
            raise ConfigError(f"{self.id}.vad_mode is invalid")
        if self.vad_mode == "gate":
            if self.vad_threshold is None or not 0 <= self.vad_threshold <= 1:
                raise ConfigError(f"{self.id}.vad_threshold is required for gated VAD")
            if self.vad_context_oldest_lag_frames is None or self.vad_context_oldest_lag_frames < 0:
                raise ConfigError(f"{self.id}.vad_context_oldest_lag_frames is required")
            if self.vad_context_newest_lag_frames is None or self.vad_context_newest_lag_frames < 0:
                raise ConfigError(f"{self.id}.vad_context_newest_lag_frames is required")
            if self.vad_context_newest_lag_frames > self.vad_context_oldest_lag_frames:
                raise ConfigError(f"{self.id}.VAD lag range is reversed")
            if self.vad_aggregate not in {"max", "mean"}:
                raise ConfigError(f"{self.id}.vad_aggregate is required for gated VAD")
        else:
            if any(
                value is not None
                for value in (
                    self.vad_threshold,
                    self.vad_context_oldest_lag_frames,
                    self.vad_context_newest_lag_frames,
                    self.vad_aggregate,
                )
            ):
                raise ConfigError(f"inactive VAD fields are not allowed for {self.id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "phrase": self.phrase,
            "wire_status": self.wire_status,
            "path": str(self.path),
            "sha256": self.sha256,
            "trigger_threshold": self.trigger_threshold,
            "evidence_window_frames": self.evidence_window_frames,
            "required_hits": self.required_hits,
            "vad_mode": self.vad_mode,
            "vad_threshold": self.vad_threshold,
            "vad_context_oldest_lag_frames": self.vad_context_oldest_lag_frames,
            "vad_context_newest_lag_frames": self.vad_context_newest_lag_frames,
            "vad_aggregate": self.vad_aggregate,
        }


@dataclass(frozen=True, slots=True)
class AudioConfig:
    device: Any
    sample_rate_hz: int
    channels: int
    dtype: str
    frame_samples: int
    queue_blocks: int
    max_callback_samples: int
    max_frame_age_ms: int
    warmup_frames: int


@dataclass(frozen=True, slots=True)
class MqttConfig:
    host: str
    port: int
    protocol: str
    client_id: str
    clean_session: bool
    keepalive_seconds: int
    qos: int
    retain: bool
    connect_timeout_seconds: float
    publish_ack_timeout_seconds: float
    reconnect_min_seconds: float
    reconnect_max_seconds: float
    contract_version: Literal["legacy", "v2"]
    resume_listening_on_reconnect: bool
    tls_enabled: bool = False
    ca_cert_path: Path | None = None
    username_env: str | None = None
    password_env: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ConfigError("mqtt.port must be between 1 and 65535")
        if not self.client_id or len(self.client_id.encode("utf-8")) > 65535:
            raise ConfigError("mqtt.client_id is empty or too long")
        if self.username_env and not self.password_env:
            raise ConfigError("mqtt.password_env is required with username_env")
        if self.password_env and not self.username_env:
            raise ConfigError("mqtt.username_env is required with password_env")


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    inference_provider: str
    onnx_threads: int
    max_consecutive_inference_errors: int
    recovery_attempts: int
    lock_root: Path
    state_store_path: Path
    max_command_age_seconds: float
    clock_skew_seconds: float
    max_event_retry_seconds: float
    outbox_max_rows: int
    outbox_max_bytes: int
    outbox_reserved_rows: int
    outbox_reserved_bytes: int
    controller_epoch: UUID | None = None


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    path: Path
    sha256: str


@dataclass(frozen=True, slots=True)
class ArtifactConfig:
    model_root: Path
    manifest_path: Path | None
    melspectrogram: ArtifactRef
    embedding: ArtifactRef
    vad: ArtifactRef | None


@dataclass(frozen=True, slots=True)
class DecisionConfig:
    arbitration_frames: int
    collision_margin: float | None
    ambiguous_suppression_frames: int
    max_vad_history_frames: int


@dataclass(frozen=True, slots=True)
class WakeWordConfig:
    environment: Literal["development", "shadow", "production"]
    room_number: str
    device_id: str
    allow_unverified_models: bool
    audio: AudioConfig
    mqtt: MqttConfig
    runtime: RuntimeConfig
    artifacts: ArtifactConfig
    decision: DecisionConfig
    models: tuple[ModelPolicy, ...]
    continue_listening_after_detection: bool = False
    source_path: Path | None = None

    def __post_init__(self) -> None:
        if len(self.models) != 2:
            raise ConfigError("exactly two wake-word models are required")
        ids = [model.id for model in self.models]
        statuses = [model.wire_status for model in self.models]
        if len(set(ids)) != len(ids) or set(ids) != set(MODEL_IDS):
            raise ConfigError("model IDs must be exactly ssafiya and nae_teon_kkeutnasseo")
        if len(set(statuses)) != len(statuses) or set(statuses) != {"call", "finish"}:
            raise ConfigError("model wire statuses must be unique call and finish")
        if self.audio.sample_rate_hz != 16000 or self.audio.channels != 1:
            raise ConfigError("capture must be 16 kHz mono")
        if self.audio.dtype != "int16" or self.audio.frame_samples != 1280:
            raise ConfigError("capture must use PCM16 frames of exactly 1,280 samples")
        if self.decision.arbitration_frames < 1:
            raise ConfigError("arbitration_frames must be >= 1")
        if self.decision.collision_margin is not None and not 0 <= self.decision.collision_margin <= 1:
            raise ConfigError("collision_margin must be null or between 0 and 1")
        for model in self.models:
            if model.vad_mode == "gate":
                assert model.vad_context_oldest_lag_frames is not None
                if model.vad_context_oldest_lag_frames >= self.decision.max_vad_history_frames:
                    raise ConfigError("VAD lag exceeds max_vad_history_frames")
        if self.mqtt.contract_version == "v2":
            if self.runtime.controller_epoch is None:
                raise ConfigError("v2 requires runtime.controller_epoch")
            if self.mqtt.clean_session:
                raise ConfigError("v2 requires a persistent MQTT session")
            if not self.runtime.state_store_path:
                raise ConfigError("v2 requires a persistent state store")
        if self.continue_listening_after_detection and self.mqtt.contract_version != "legacy":
            raise ConfigError("continue_listening_after_detection currently requires legacy MQTT")
        if self.environment == "production" and self.allow_unverified_models:
            raise ConfigError("production cannot allow unverified models")
        if self.environment == "production":
            if str(self.runtime.lock_root).startswith("/tmp"):
                raise ConfigError("production lock root must be host-shared, not /tmp")
            if str(self.runtime.state_store_path).startswith("/tmp"):
                raise ConfigError("production state store must use persistent local storage")

    @property
    def model_by_id(self) -> dict[str, ModelPolicy]:
        return {model.id: model for model in self.models}

    @property
    def config_revision(self) -> str:
        return "sha256:" + sha256(canonical_json(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        mqtt_dict = {
            "host": self.mqtt.host,
            "port": self.mqtt.port,
            "protocol": self.mqtt.protocol,
            "client_id": self.mqtt.client_id,
            "clean_session": self.mqtt.clean_session,
            "keepalive_seconds": self.mqtt.keepalive_seconds,
            "qos": self.mqtt.qos,
            "retain": self.mqtt.retain,
            "connect_timeout_seconds": self.mqtt.connect_timeout_seconds,
            "publish_ack_timeout_seconds": self.mqtt.publish_ack_timeout_seconds,
            "reconnect_min_seconds": self.mqtt.reconnect_min_seconds,
            "reconnect_max_seconds": self.mqtt.reconnect_max_seconds,
            "contract_version": self.mqtt.contract_version,
            "resume_listening_on_reconnect": self.mqtt.resume_listening_on_reconnect,
            "tls_enabled": self.mqtt.tls_enabled,
            "ca_cert_path": str(self.mqtt.ca_cert_path) if self.mqtt.ca_cert_path else None,
            "username_env": self.mqtt.username_env,
            "password_env": self.mqtt.password_env,
        }
        return {
            "environment": self.environment,
            "room_number": self.room_number,
            "device_id": self.device_id,
            "allow_unverified_models": self.allow_unverified_models,
            "continue_listening_after_detection": self.continue_listening_after_detection,
            "audio": {
                "device": self.audio.device,
                "sample_rate_hz": self.audio.sample_rate_hz,
                "channels": self.audio.channels,
                "dtype": self.audio.dtype,
                "frame_samples": self.audio.frame_samples,
                "queue_blocks": self.audio.queue_blocks,
                "max_callback_samples": self.audio.max_callback_samples,
                "max_frame_age_ms": self.audio.max_frame_age_ms,
                "warmup_frames": self.audio.warmup_frames,
            },
            "mqtt": mqtt_dict,
            "runtime": {
                "inference_provider": self.runtime.inference_provider,
                "onnx_threads": self.runtime.onnx_threads,
                "max_consecutive_inference_errors": self.runtime.max_consecutive_inference_errors,
                "recovery_attempts": self.runtime.recovery_attempts,
                "lock_root": str(self.runtime.lock_root),
                "state_store_path": str(self.runtime.state_store_path),
                "max_command_age_seconds": self.runtime.max_command_age_seconds,
                "clock_skew_seconds": self.runtime.clock_skew_seconds,
                "max_event_retry_seconds": self.runtime.max_event_retry_seconds,
                "outbox_max_rows": self.runtime.outbox_max_rows,
                "outbox_max_bytes": self.runtime.outbox_max_bytes,
                "outbox_reserved_rows": self.runtime.outbox_reserved_rows,
                "outbox_reserved_bytes": self.runtime.outbox_reserved_bytes,
                "controller_epoch": str(self.runtime.controller_epoch) if self.runtime.controller_epoch else None,
            },
            "artifacts": {
                "model_root": str(self.artifacts.model_root),
                "manifest_path": str(self.artifacts.manifest_path) if self.artifacts.manifest_path else None,
                "melspectrogram": {
                    "path": str(self.artifacts.melspectrogram.path),
                    "sha256": self.artifacts.melspectrogram.sha256,
                },
                "embedding": {
                    "path": str(self.artifacts.embedding.path),
                    "sha256": self.artifacts.embedding.sha256,
                },
                "vad": (
                    {
                        "path": str(self.artifacts.vad.path),
                        "sha256": self.artifacts.vad.sha256,
                    }
                    if self.artifacts.vad
                    else None
                ),
            },
            "decision": {
                "arbitration_frames": self.decision.arbitration_frames,
                "collision_margin": self.decision.collision_margin,
                "ambiguous_suppression_frames": self.decision.ambiguous_suppression_frames,
                "max_vad_history_frames": self.decision.max_vad_history_frames,
            },
            "models": [model.to_dict() for model in self.models],
        }


def _resolve_path(value: Any, base_dir: Path, name: str) -> Path:
    path = Path(_text(value, name))
    return path if path.is_absolute() else (base_dir / path).resolve()


def _parse_model(raw: Any, model_root: Path, index: int) -> ModelPolicy:
    value = _keys(
        raw,
        {
            "id", "phrase", "wire_status", "path", "sha256", "trigger_threshold",
            "evidence_window_frames", "required_hits", "vad_mode", "vad_threshold",
            "vad_context_oldest_lag_frames", "vad_context_newest_lag_frames", "vad_aggregate",
        },
        f"models[{index}]",
    )
    vad_mode = _text(_required(value, "vad_mode", f"models[{index}]"), f"models[{index}].vad_mode")
    return ModelPolicy(
        id=_text(_required(value, "id", f"models[{index}]"), f"models[{index}].id"),
        phrase=_text(_required(value, "phrase", f"models[{index}]"), f"models[{index}].phrase"),
        wire_status=_text(_required(value, "wire_status", f"models[{index}]"), f"models[{index}].wire_status"),  # type: ignore[arg-type]
        path=_resolve_path(_required(value, "path", f"models[{index}]"), model_root, f"models[{index}].path"),
        sha256=_text(_required(value, "sha256", f"models[{index}]"), f"models[{index}].sha256"),
        trigger_threshold=_float(_required(value, "trigger_threshold", f"models[{index}]"), f"models[{index}].trigger_threshold", minimum=0, maximum=1),
        evidence_window_frames=_int(_required(value, "evidence_window_frames", f"models[{index}]"), minimum=1, name=f"models[{index}].evidence_window_frames"),
        required_hits=_int(_required(value, "required_hits", f"models[{index}]"), minimum=1, name=f"models[{index}].required_hits"),
        vad_mode=vad_mode,  # type: ignore[arg-type]
        vad_threshold=None if value.get("vad_threshold") is None else _float(value["vad_threshold"], f"models[{index}].vad_threshold", minimum=0, maximum=1),
        vad_context_oldest_lag_frames=None if value.get("vad_context_oldest_lag_frames") is None else _int(value["vad_context_oldest_lag_frames"], minimum=0, name=f"models[{index}].vad_context_oldest_lag_frames"),
        vad_context_newest_lag_frames=None if value.get("vad_context_newest_lag_frames") is None else _int(value["vad_context_newest_lag_frames"], minimum=0, name=f"models[{index}].vad_context_newest_lag_frames"),
        vad_aggregate=value.get("vad_aggregate"),  # type: ignore[arg-type]
    )


def load_config(path: str | Path, *, allow_environment_override: bool = True) -> WakeWordConfig:
    source_path = Path(path).resolve()
    try:
        raw = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read config: {source_path}") from exc
    root = _keys(raw, {"environment", "room_number", "device_id", "allow_unverified_models", "continue_listening_after_detection", "audio", "mqtt", "runtime", "artifacts", "decision", "models"}, "config")
    environment = _text(_required(root, "environment", "config"), "environment")
    if environment not in {"development", "shadow", "production"}:
        raise ConfigError("environment must be development, shadow, or production")
    room = _text(_required(root, "room_number", "config"), "room_number")
    if room != room.strip() or not room or any(char in room for char in "/+#\x00") or any(ord(char) < 32 for char in room):
        raise ConfigError("room_number contains forbidden characters")
    device_id = _text(_required(root, "device_id", "config"), "device_id")
    if device_id != device_id.strip() or any(ord(char) < 32 for char in device_id):
        raise ConfigError("device_id contains forbidden characters")
    allow_unverified = _bool(_required(root, "allow_unverified_models", "config"), "allow_unverified_models")
    if allow_environment_override and os.environ.get("WAKEWORD_ALLOW_UNVERIFIED_MODELS", "").lower() == "true":
        allow_unverified = True
    continue_listening = _bool(
        root.get("continue_listening_after_detection", False),
        "continue_listening_after_detection",
    )

    audio_raw = _keys(_required(root, "audio", "config"), {"device", "sample_rate_hz", "channels", "dtype", "frame_samples", "queue_blocks", "max_callback_samples", "max_frame_age_ms", "warmup_frames"}, "audio")
    audio = AudioConfig(
        device=audio_raw.get("device", "default"),
        sample_rate_hz=_int(_required(audio_raw, "sample_rate_hz", "audio"), minimum=1, name="audio.sample_rate_hz"),
        channels=_int(_required(audio_raw, "channels", "audio"), minimum=1, name="audio.channels"),
        dtype=_text(_required(audio_raw, "dtype", "audio"), "audio.dtype"),
        frame_samples=_int(_required(audio_raw, "frame_samples", "audio"), minimum=1, name="audio.frame_samples"),
        queue_blocks=_int(_required(audio_raw, "queue_blocks", "audio"), minimum=1, name="audio.queue_blocks"),
        max_callback_samples=_int(_required(audio_raw, "max_callback_samples", "audio"), minimum=1, name="audio.max_callback_samples"),
        max_frame_age_ms=_int(_required(audio_raw, "max_frame_age_ms", "audio"), minimum=1, name="audio.max_frame_age_ms"),
        warmup_frames=_int(_required(audio_raw, "warmup_frames", "audio"), minimum=25, name="audio.warmup_frames"),
    )

    mqtt_raw = _keys(_required(root, "mqtt", "config"), {"host", "port", "protocol", "client_id", "clean_session", "keepalive_seconds", "qos", "retain", "connect_timeout_seconds", "publish_ack_timeout_seconds", "reconnect_min_seconds", "reconnect_max_seconds", "contract_version", "resume_listening_on_reconnect", "tls_enabled", "ca_cert_path", "username_env", "password_env"}, "mqtt")
    contract_version = _text(_required(mqtt_raw, "contract_version", "mqtt"), "mqtt.contract_version")
    if contract_version not in {"legacy", "v2"}:
        raise ConfigError("mqtt.contract_version must be legacy or v2")
    mqtt = MqttConfig(
        host=_text(_required(mqtt_raw, "host", "mqtt"), "mqtt.host"),
        port=_int(_required(mqtt_raw, "port", "mqtt"), minimum=1, name="mqtt.port"),
        protocol=_text(_required(mqtt_raw, "protocol", "mqtt"), "mqtt.protocol"),
        client_id=_text(_required(mqtt_raw, "client_id", "mqtt"), "mqtt.client_id"),
        clean_session=_bool(_required(mqtt_raw, "clean_session", "mqtt"), "mqtt.clean_session"),
        keepalive_seconds=_int(_required(mqtt_raw, "keepalive_seconds", "mqtt"), minimum=1, name="mqtt.keepalive_seconds"),
        qos=_int(_required(mqtt_raw, "qos", "mqtt"), minimum=0, name="mqtt.qos"),
        retain=_bool(_required(mqtt_raw, "retain", "mqtt"), "mqtt.retain"),
        connect_timeout_seconds=_float(_required(mqtt_raw, "connect_timeout_seconds", "mqtt"), minimum=0.1, name="mqtt.connect_timeout_seconds"),
        publish_ack_timeout_seconds=_float(_required(mqtt_raw, "publish_ack_timeout_seconds", "mqtt"), minimum=0.1, name="mqtt.publish_ack_timeout_seconds"),
        reconnect_min_seconds=_float(_required(mqtt_raw, "reconnect_min_seconds", "mqtt"), minimum=0.1, name="mqtt.reconnect_min_seconds"),
        reconnect_max_seconds=_float(_required(mqtt_raw, "reconnect_max_seconds", "mqtt"), minimum=0.1, name="mqtt.reconnect_max_seconds"),
        contract_version=contract_version,  # type: ignore[arg-type]
        resume_listening_on_reconnect=_bool(_required(mqtt_raw, "resume_listening_on_reconnect", "mqtt"), "mqtt.resume_listening_on_reconnect"),
        tls_enabled=_bool(mqtt_raw.get("tls_enabled", False), "mqtt.tls_enabled"),
        ca_cert_path=None if mqtt_raw.get("ca_cert_path") is None else _resolve_path(mqtt_raw["ca_cert_path"], source_path.parent, "mqtt.ca_cert_path"),
        username_env=None if mqtt_raw.get("username_env") is None else _text(mqtt_raw["username_env"], "mqtt.username_env"),
        password_env=None if mqtt_raw.get("password_env") is None else _text(mqtt_raw["password_env"], "mqtt.password_env"),
    )
    if mqtt.reconnect_max_seconds < mqtt.reconnect_min_seconds:
        raise ConfigError("mqtt.reconnect_max_seconds must be >= reconnect_min_seconds")
    if mqtt.qos != 1 or mqtt.retain:
        raise ConfigError("wake topics require QoS 1 and retain=false")
    if environment == "production" and not mqtt.tls_enabled:
        raise ConfigError("production MQTT requires TLS")

    runtime_raw = _keys(_required(root, "runtime", "config"), {"inference_provider", "onnx_threads", "max_consecutive_inference_errors", "recovery_attempts", "lock_root", "state_store_path", "max_command_age_seconds", "clock_skew_seconds", "max_event_retry_seconds", "outbox_max_rows", "outbox_max_bytes", "outbox_reserved_rows", "outbox_reserved_bytes", "controller_epoch"}, "runtime")
    epoch_value = runtime_raw.get("controller_epoch")
    if epoch_value is None:
        epoch = None
    else:
        try:
            epoch = UUID(_text(epoch_value, "runtime.controller_epoch"))
        except ValueError as exc:
            raise ConfigError("runtime.controller_epoch must be a UUID") from exc
    runtime = RuntimeConfig(
        inference_provider=_text(_required(runtime_raw, "inference_provider", "runtime"), "runtime.inference_provider"),
        onnx_threads=_int(_required(runtime_raw, "onnx_threads", "runtime"), minimum=1, name="runtime.onnx_threads"),
        max_consecutive_inference_errors=_int(_required(runtime_raw, "max_consecutive_inference_errors", "runtime"), minimum=1, name="runtime.max_consecutive_inference_errors"),
        recovery_attempts=_int(_required(runtime_raw, "recovery_attempts", "runtime"), minimum=1, name="runtime.recovery_attempts"),
        lock_root=_resolve_path(_required(runtime_raw, "lock_root", "runtime"), source_path.parent, "runtime.lock_root"),
        state_store_path=_resolve_path(_required(runtime_raw, "state_store_path", "runtime"), source_path.parent, "runtime.state_store_path"),
        max_command_age_seconds=_float(_required(runtime_raw, "max_command_age_seconds", "runtime"), minimum=0.001, name="runtime.max_command_age_seconds"),
        clock_skew_seconds=_float(_required(runtime_raw, "clock_skew_seconds", "runtime"), minimum=0, name="runtime.clock_skew_seconds"),
        max_event_retry_seconds=_float(_required(runtime_raw, "max_event_retry_seconds", "runtime"), minimum=0.1, name="runtime.max_event_retry_seconds"),
        outbox_max_rows=_int(_required(runtime_raw, "outbox_max_rows", "runtime"), minimum=1, name="runtime.outbox_max_rows"),
        outbox_max_bytes=_int(_required(runtime_raw, "outbox_max_bytes", "runtime"), minimum=1, name="runtime.outbox_max_bytes"),
        outbox_reserved_rows=_int(_required(runtime_raw, "outbox_reserved_rows", "runtime"), minimum=1, name="runtime.outbox_reserved_rows"),
        outbox_reserved_bytes=_int(_required(runtime_raw, "outbox_reserved_bytes", "runtime"), minimum=1, name="runtime.outbox_reserved_bytes"),
        controller_epoch=epoch,
    )
    if runtime.outbox_reserved_rows >= runtime.outbox_max_rows or runtime.outbox_reserved_bytes >= runtime.outbox_max_bytes:
        raise ConfigError("outbox reservation must leave room for ordinary backlog")

    artifacts_raw = _keys(_required(root, "artifacts", "config"), {"model_root", "manifest_path", "melspectrogram", "embedding", "vad"}, "artifacts")
    model_root = _resolve_path(_required(artifacts_raw, "model_root", "artifacts"), source_path.parent, "artifacts.model_root")

    def artifact_ref(name: str) -> ArtifactRef:
        raw_ref = _keys(_required(artifacts_raw, name, "artifacts"), {"path", "sha256"}, f"artifacts.{name}")
        return ArtifactRef(
            path=_resolve_path(_required(raw_ref, "path", f"artifacts.{name}"), model_root, f"artifacts.{name}.path"),
            sha256=_text(_required(raw_ref, "sha256", f"artifacts.{name}"), f"artifacts.{name}.sha256"),
        )

    manifest_value = artifacts_raw.get("manifest_path")
    manifest_path = None if manifest_value is None else _resolve_path(manifest_value, source_path.parent, "artifacts.manifest_path")
    vad_value = artifacts_raw.get("vad")
    vad = None if vad_value is None else artifact_ref("vad")
    artifacts = ArtifactConfig(model_root, manifest_path, artifact_ref("melspectrogram"), artifact_ref("embedding"), vad)

    decision_raw = _keys(_required(root, "decision", "config"), {"arbitration_frames", "collision_margin", "ambiguous_suppression_frames", "max_vad_history_frames"}, "decision")
    margin = decision_raw.get("collision_margin")
    decision = DecisionConfig(
        arbitration_frames=_int(_required(decision_raw, "arbitration_frames", "decision"), minimum=1, name="decision.arbitration_frames"),
        collision_margin=None if margin is None else _float(margin, "decision.collision_margin", minimum=0, maximum=1),
        ambiguous_suppression_frames=_int(_required(decision_raw, "ambiguous_suppression_frames", "decision"), minimum=0, name="decision.ambiguous_suppression_frames"),
        max_vad_history_frames=_int(_required(decision_raw, "max_vad_history_frames", "decision"), minimum=1, name="decision.max_vad_history_frames"),
    )
    raw_models = _required(root, "models", "config")
    if not isinstance(raw_models, list):
        raise ConfigError("models must be a list")
    models = tuple(_parse_model(value, model_root, index) for index, value in enumerate(raw_models))
    config = WakeWordConfig(
        environment=environment,
        room_number=room,
        device_id=device_id,
        allow_unverified_models=allow_unverified,
        audio=audio,
        mqtt=mqtt,
        runtime=runtime,
        artifacts=artifacts,
        decision=decision,
        models=models,
        continue_listening_after_detection=continue_listening,
        source_path=source_path,
    )
    return config
