"""WakeWordModule public API.

The package deliberately keeps audio/model ownership separate from MQTT and
state coordination.  Importing this module does not initialize a microphone,
ONNX runtime, or network client.
"""

from .contracts import (
    AudioBlock,
    AudioFrame,
    InternalState,
    RawScores,
    WakeWordCandidate,
    WakeWordDetection,
    canonical_json,
    legacy_status_payload,
)
from .config import WakeWordConfig, load_config
from .detector import DetectionStateMachine
from .framing import PcmFrameAssembler

__all__ = [
    "AudioBlock",
    "AudioFrame",
    "DetectionStateMachine",
    "InternalState",
    "PcmFrameAssembler",
    "RawScores",
    "WakeWordCandidate",
    "WakeWordConfig",
    "WakeWordDetection",
    "canonical_json",
    "legacy_status_payload",
    "load_config",
]
