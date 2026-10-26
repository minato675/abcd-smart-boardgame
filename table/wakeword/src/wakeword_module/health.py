"""Bounded metrics and sanitized operational health reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import time
from typing import Any, Mapping

from .coordinator import HealthState


@dataclass
class Metrics:
    counters: dict[str, int] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)

    def inc(self, name: str, value: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + value

    def set(self, name: str, value: float | int) -> None:
        self.gauges[name] = float(value)

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        return {"counters": dict(self.counters), "gauges": dict(self.gauges)}


def health_payload(state: HealthState, *, config_revision: str, service_version: str = "0.1.0") -> dict[str, Any]:
    return {
        "service": "wakeword-module",
        "version": service_version,
        "configRevision": config_revision,
        "live": state.live,
        "ready": state.ready,
        "state": state.state,
        "brokerConnected": state.broker_connected,
        "audioActive": state.audio_active,
        "modelQuality": state.model_quality,
        "reason": state.reason,
    }


class JsonLogFormatter(logging.Formatter):
    """Allow only bounded operational fields; never serialize exception objects."""

    ALLOWED = {
        "old_state", "new_state", "reason", "event_id", "command_id", "listen_session_id",
        "model_id", "model_hash_prefix", "score", "threshold", "sequence", "discontinuities",
        "mqtt_result", "error_type", "config_revision", "room_number", "device_id",
        "generation", "frame_end_sample_index", "vad_score", "ssafiya_score",
        "nae_teon_kkeutnasseo_score", "component", "topic", "byte_count", "result",
        "config_path", "environment", "model_quality", "audio_device", "host_api",
        "sample_rate_hz", "channels", "mqtt_host", "mqtt_port", "command_kind", "state",
        "pcm_rms", "pcm_peak", "pcm_mean",
    }

    def format(self, record: logging.LogRecord) -> str:
        value: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in self.ALLOWED:
            item = getattr(record, key, None)
            if item is not None:
                if isinstance(item, str) and len(item) > 128:
                    item = item[:128]
                value[key] = item
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
