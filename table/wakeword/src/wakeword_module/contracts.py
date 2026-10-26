"""Small immutable data contracts and strict MQTT JSON helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import math
import re
from types import MappingProxyType
from typing import Any, Literal, Mapping
from uuid import UUID

import numpy as np


MAX_MQTT_PAYLOAD_BYTES = 4096
MAX_SEQUENCE = 2**63 - 1
WIRE_STATUSES = ("idle", "listening", "call", "finish")
MODEL_IDS = ("ssafiya", "nae_teon_kkeutnasseo")
_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class InternalState(str, Enum):
    STARTING = "starting"
    IDLE = "idle"
    ARMING_START = "arming_start"
    RECOVERING_AUDIO = "recovering_audio"
    LISTENING = "listening"
    LATCHED_CALL = "latched_call"
    LATCHED_FINISH = "latched_finish"
    PAUSED_DISCONNECTED = "paused_disconnected"
    FAULT = "fault"
    SHUTTING_DOWN = "shutting_down"


class ContractError(ValueError):
    """A sanitized protocol/configuration error safe to expose as a reason code."""

    def __init__(self, message: str, reason_code: str = "invalid_schema") -> None:
        super().__init__(message)
        self.reason_code = reason_code


class DuplicateJsonKeyError(ContractError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError("duplicate JSON member name")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise ContractError("non-finite JSON number")


def strict_json_loads(payload: bytes | str, *, max_bytes: int = MAX_MQTT_PAYLOAD_BYTES) -> Any:
    """Decode JSON with bounded UTF-8, duplicate-key, and finite-number checks."""

    if isinstance(payload, bytes):
        if len(payload) > max_bytes:
            raise ContractError("payload exceeds maximum size", "invalid_schema")
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ContractError("payload is not valid UTF-8") from exc
    elif isinstance(payload, str):
        text = payload
        if len(text.encode("utf-8")) > max_bytes:
            raise ContractError("payload exceeds maximum size", "invalid_schema")
    else:
        raise ContractError("payload must be UTF-8 bytes or text", "invalid_schema")
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except ContractError:
        raise
    except (TypeError, json.JSONDecodeError) as exc:
        raise ContractError("malformed JSON") from exc


def canonical_json(value: Any) -> bytes:
    """Return deterministic JSON bytes for digesting validated protocol values.

    The v2 schemas only permit strings, integers, booleans, null, arrays, and
    objects.  With those values this sorted, compact encoding is equivalent to
    the RFC 8785 representation used by the protocol profile.
    """

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("value cannot be canonically encoded") from exc


def parse_utc_timestamp(value: Any, field: str = "timestamp") -> datetime:
    if not isinstance(value, str) or not _RFC3339_RE.fullmatch(value):
        raise ContractError(f"{field} must be an RFC 3339 timestamp with an explicit offset")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} is not a valid timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def parse_uuid(value: Any, field: str) -> UUID:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be a UUID")
    try:
        return UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ContractError(f"{field} must be a UUID") from exc


def _require_exact_object(value: Any, expected: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("top-level JSON value must be an object")
    actual = set(value)
    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        detail = []
        if missing:
            detail.append("missing " + ",".join(sorted(missing)))
        if extra:
            detail.append("unknown " + ",".join(sorted(extra)))
        raise ContractError("invalid object fields: " + "; ".join(detail))
    return value


@dataclass(frozen=True, slots=True)
class AudioBlock:
    generation: int
    first_sample_index: int
    callback_monotonic_ns: int
    adc_time_seconds: float | None
    pcm_bytes: bytes

    def __post_init__(self) -> None:
        if self.generation < 0 or self.first_sample_index < 0:
            raise ValueError("audio indexes must be non-negative")
        if self.callback_monotonic_ns < 0:
            raise ValueError("callback monotonic time must be non-negative")
        if len(self.pcm_bytes) == 0 or len(self.pcm_bytes) % 2:
            raise ValueError("AudioBlock must contain a non-empty even number of PCM16 bytes")
        object.__setattr__(self, "pcm_bytes", bytes(self.pcm_bytes))

    @property
    def sample_count(self) -> int:
        return len(self.pcm_bytes) // 2


@dataclass(frozen=True, slots=True)
class AudioFrame:
    generation: int
    sequence: int
    first_sample_index: int
    end_sample_index: int
    frame_end_monotonic_ns: int
    pcm: np.ndarray

    def __post_init__(self) -> None:
        if self.generation < 0 or self.sequence < 0 or self.first_sample_index < 0:
            raise ValueError("audio frame indexes must be non-negative")
        if self.end_sample_index != self.first_sample_index + 1280:
            raise ValueError("audio frame sample indexes must span exactly 1,280 samples")
        if self.frame_end_monotonic_ns < 0:
            raise ValueError("audio frame monotonic time must be non-negative")
        pcm = np.ascontiguousarray(self.pcm, dtype=np.int16).copy()
        if pcm.shape != (1280,):
            raise ValueError("AudioFrame must contain exactly 1,280 samples")
        pcm.setflags(write=False)
        object.__setattr__(self, "pcm", pcm)


@dataclass(frozen=True, slots=True)
class RawScores:
    generation: int
    sequence: int
    frame_end_sample_index: int
    frame_end_monotonic_ns: int
    scores: Mapping[str, float]
    vad_score: float | None = None
    occurred_at_utc: datetime | None = None
    timestamp_uncertainty_ms: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "scores", MappingProxyType(dict(self.scores)))


@dataclass(frozen=True, slots=True)
class WakeWordCandidate:
    generation: int
    model_id: Literal["ssafiya", "nae_teon_kkeutnasseo"]
    wire_status: Literal["call", "finish"]
    raw_score: float
    threshold: float
    frame_end_sample_index: int
    frame_end_monotonic_ns: int
    occurred_at_utc: datetime
    timestamp_uncertainty_ms: float


@dataclass(frozen=True, slots=True)
class WakeWordDetection:
    event_id: UUID
    listen_session_id: UUID
    status_revision: int
    candidate: WakeWordCandidate
    model_sha256: str
    config_revision: str


@dataclass(frozen=True, slots=True)
class V2Command:
    kind: Literal["start", "stop", "request-status"]
    contract_version: int
    command_id: UUID | None
    request_id: UUID | None
    controller_epoch: UUID | None
    command_sequence: int | None
    listen_session_id: UUID | None
    issued_at: datetime
    raw: Mapping[str, Any]

    @property
    def identity_id(self) -> UUID:
        value = self.command_id or self.request_id
        if value is None:
            raise RuntimeError("validated v2 command has no identity")
        return value

    @property
    def digest(self) -> bytes:
        return canonical_json(self.raw)


def parse_legacy_command(payload: bytes | str) -> None:
    """Validate the deliberately empty legacy command body.

    The topic supplies the command meaning.  A successful result is ``None``
    because the body intentionally carries no state or identity.
    """

    if isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        raw = bytes(payload)
    if len(raw) > MAX_MQTT_PAYLOAD_BYTES:
        raise ContractError("payload exceeds maximum size")
    if raw.strip(b" \t\r\n") == b"":
        return None
    value = strict_json_loads(raw)
    if value != {}:
        raise ContractError("legacy command body must be empty or {}")
    return None


def parse_v2_command(kind: str, payload: bytes | str) -> V2Command:
    if kind not in {"start", "stop", "request-status"}:
        raise ValueError(f"unknown command kind: {kind}")
    value = strict_json_loads(payload)
    if kind in {"start", "stop"}:
        expected = {
            "contractVersion",
            "commandId",
            "controllerEpoch",
            "commandSequence",
            "listenSessionId",
            "issuedAt",
        }
    else:
        expected = {"contractVersion", "requestId", "issuedAt"}
    obj = _require_exact_object(value, expected)
    if obj["contractVersion"] != 2 or isinstance(obj["contractVersion"], bool):
        raise ContractError("unsupported contract version", "unsupported_version")
    issued_at = parse_utc_timestamp(obj["issuedAt"], "issuedAt")
    if kind in {"start", "stop"}:
        command_id = parse_uuid(obj["commandId"], "commandId")
        epoch = parse_uuid(obj["controllerEpoch"], "controllerEpoch")
        session = parse_uuid(obj["listenSessionId"], "listenSessionId")
        sequence = obj["commandSequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or not 0 <= sequence <= MAX_SEQUENCE:
            raise ContractError("commandSequence is outside the permitted integer range")
        return V2Command(
            kind=kind,
            contract_version=2,
            command_id=command_id,
            request_id=None,
            controller_epoch=epoch,
            command_sequence=sequence,
            listen_session_id=session,
            issued_at=issued_at,
            raw=obj,
        )
    request_id = parse_uuid(obj["requestId"], "requestId")
    return V2Command(
        kind=kind,
        contract_version=2,
        command_id=None,
        request_id=request_id,
        controller_epoch=None,
        command_sequence=None,
        listen_session_id=None,
        issued_at=issued_at,
        raw=obj,
    )


def parse_v2_ack(payload: bytes | str) -> dict[str, Any]:
    value = strict_json_loads(payload)
    obj = _require_exact_object(
        value,
        {"contractVersion", "ackId", "eventId", "listenSessionId", "receivedAt"},
    )
    if obj["contractVersion"] != 2 or isinstance(obj["contractVersion"], bool):
        raise ContractError("unsupported contract version", "unsupported_version")
    for field in ("ackId", "eventId", "listenSessionId"):
        parse_uuid(obj[field], field)
    parse_utc_timestamp(obj["receivedAt"], "receivedAt")
    return obj


def legacy_status_payload(status: str) -> bytes:
    if status not in WIRE_STATUSES:
        raise ValueError(f"invalid wire status: {status}")
    return json.dumps(
        {"status": status}, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


V2_STATUS_FIELDS = (
    "contractVersion",
    "deviceId",
    "statusRevision",
    "status",
    "listenSessionId",
    "eventId",
    "occurredAt",
    "modelId",
    "modelSha256",
    "confidence",
    "configRevision",
    "commandId",
    "requestId",
    "outcome",
    "reasonCode",
)


def serialize_v2_status(value: Mapping[str, Any]) -> bytes:
    if set(value) != set(V2_STATUS_FIELDS):
        raise ContractError("v2 status must contain exactly the fixed envelope fields")
    if value["contractVersion"] != 2 or value["status"] not in WIRE_STATUSES:
        raise ContractError("invalid v2 status version or status")
    if isinstance(value["statusRevision"], bool) or not isinstance(value["statusRevision"], int) or not 0 <= value["statusRevision"] <= MAX_SEQUENCE:
        raise ContractError("invalid v2 status revision")
    if not isinstance(value["deviceId"], str) or not value["deviceId"]:
        raise ContractError("invalid v2 device ID")
    parse_utc_timestamp(value["occurredAt"], "occurredAt")
    for field in ("listenSessionId", "eventId", "commandId", "requestId"):
        if value[field] is not None:
            parse_uuid(value[field], field)
    if (value["commandId"] is None) == (value["requestId"] is None) and value["outcome"] in {"accepted", "duplicate", "in_progress", "rejected", "snapshot"}:
        raise ContractError("v2 response must correlate exactly one command or request")
    status = value["status"]
    if status == "idle":
        if any(value[field] is not None for field in ("listenSessionId", "eventId", "modelId", "modelSha256", "confidence")):
            raise ContractError("idle v2 status cannot carry session/event/model data")
    elif status == "listening":
        if value["listenSessionId"] is None or any(value[field] is not None for field in ("eventId", "modelId", "modelSha256", "confidence")):
            raise ContractError("listening v2 status has invalid identity fields")
    else:
        if any(value[field] is None for field in ("listenSessionId", "eventId", "modelId", "modelSha256", "confidence")):
            raise ContractError("latched v2 status is missing event identity")
        if value["modelId"] not in MODEL_IDS or not isinstance(value["modelSha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["modelSha256"]):
            raise ContractError("latched v2 status has invalid model identity")
    outcome = value["outcome"]
    if outcome not in {None, "accepted", "duplicate", "in_progress", "rejected", "snapshot"}:
        raise ContractError("invalid v2 outcome")
    reason_codes = {"invalid_schema", "unsupported_version", "expired", "future_issued_at", "stale_command", "sequence_conflict", "controller_epoch_mismatch", "stale_session", "session_reuse", "event_unacknowledged", "invalid_state", "interrupted", "id_conflict"}
    if value["reasonCode"] is not None and value["reasonCode"] not in reason_codes:
        raise ContractError("invalid v2 reasonCode")
    if value["reasonCode"] is not None and outcome != "rejected":
        raise ContractError("reasonCode is only valid on rejected responses")
    confidence = value["confidence"]
    if confidence is not None and (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(float(confidence))
        or not 0 <= float(confidence) <= 1
    ):
        raise ContractError("invalid v2 confidence")
    rendered = json.dumps(
        dict(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(rendered) > MAX_MQTT_PAYLOAD_BYTES:
        raise ContractError("v2 status exceeds maximum payload size")
    return rendered
