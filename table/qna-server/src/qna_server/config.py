from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    username: str
    password: str
    client_id: str
    qos: int
    rule_dir: Path
    publish_wake_start: bool
    gms_api_key: str
    gms_auth_header: str
    gms_auth_scheme: str
    gms_base_url: str
    gms_chat_endpoint: str
    gms_stt_endpoint: str
    gms_tts_endpoint: str
    gms_embedding_endpoint: str
    gms_models_endpoint: str
    gms_gemini_audio_base_url: str
    gms_gemini_audio_endpoint: str
    gms_gemini_audio_request_style: str
    gms_text_model: str
    gms_stt_model: str
    gms_tts_model: str
    gms_embedding_model: str
    gms_gemini_audio_model: str
    gms_voice: str
    gms_tts_response_format: str
    gms_temperature: float
    elevenlabs_api_key: str
    elevenlabs_base_url: str
    elevenlabs_voice_id: str
    elevenlabs_model_id: str
    elevenlabs_output_format: str
    elevenlabs_stability: float
    elevenlabs_similarity_boost: float
    elevenlabs_style: float
    elevenlabs_use_speaker_boost: bool
    elevenlabs_timeout_seconds: float
    vector_backend: str
    retrieval_mode: str
    vector_index_path: Path
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str
    qdrant_timeout_seconds: float
    llm_streaming: bool
    stt_mode: str
    audio_file: str
    mic_start_delay_seconds: float
    record_seconds: float
    record_min_seconds: float
    record_sample_rate: int
    record_channels: int
    input_device: str
    record_silence_seconds: float
    record_silence_threshold: int
    record_noise_seconds: float
    record_threshold_multiplier: float
    tts_mode: str
    tts_output_dir: Path
    tts_play_audio: bool
    tts_streaming: bool
    ready_sound_enabled: bool
    ready_sound_frequency: int
    ready_sound_duration_seconds: float
    ready_sound_volume: float
    ready_sound_output_device: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.getenv("MQTT_HOST", "i15a402.p.ssafy.io"),
            port=_env_int("MQTT_PORT", 8113),
            username=os.getenv("MQTT_USERNAME", "ssafy"),
            password=os.getenv("MQTT_PASSWORD", "ssafy"),
            client_id=os.getenv("MQTT_CLIENT_ID", f"qna-server-{uuid.uuid4().hex[:8]}"),
            qos=_env_int("MQTT_QOS", 1),
            rule_dir=Path(os.getenv("QNA_RULE_DIR", str(PROJECT_ROOT / "rules"))),
            publish_wake_start=_env_bool("QNA_PUBLISH_WAKE_START", True),
            gms_api_key=_first_env(
                "GMS_API_KEY",
                "GENAI_API_KEY",
                "GEN_AI_API_KEY",
            ),
            gms_auth_header=os.getenv("GMS_AUTH_HEADER", "Authorization"),
            gms_auth_scheme=os.getenv("GMS_AUTH_SCHEME", "Bearer"),
            gms_base_url=os.getenv("GMS_BASE_URL", ""),
            gms_chat_endpoint=os.getenv("GMS_CHAT_ENDPOINT", "/v1/chat/completions"),
            gms_stt_endpoint=os.getenv("GMS_STT_ENDPOINT", "/v1/audio/transcriptions"),
            gms_tts_endpoint=os.getenv("GMS_TTS_ENDPOINT", "/v1/audio/speech"),
            gms_embedding_endpoint=os.getenv("GMS_EMBEDDING_ENDPOINT", "/v1/embeddings"),
            gms_models_endpoint=os.getenv("GMS_MODELS_ENDPOINT", "/v1/models"),
            gms_gemini_audio_base_url=os.getenv(
                "GMS_GEMINI_AUDIO_BASE_URL",
                "https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com",
            ),
            gms_gemini_audio_endpoint=os.getenv("GMS_GEMINI_AUDIO_ENDPOINT", ""),
            gms_gemini_audio_request_style=os.getenv("GMS_GEMINI_AUDIO_REQUEST_STYLE", "generate-content"),
            gms_text_model=os.getenv("GMS_TEXT_MODEL", "gpt-4.1-nano"),
            gms_stt_model=os.getenv("GMS_STT_MODEL", "whisper-1"),
            gms_tts_model=os.getenv("GMS_TTS_MODEL", "gpt-4o-mini-tts"),
            gms_embedding_model=os.getenv("GMS_EMBEDDING_MODEL", "text-embedding-3-small"),
            gms_gemini_audio_model=(
                _first_env("GMS_GEMINI_AUDIO_MODEL", "GMS_GEMINI_AUDIO_STT_MODEL")
                or "gemini-2.5-flash"
            ),
            gms_voice=os.getenv("GMS_TTS_VOICE", "alloy"),
            gms_tts_response_format=os.getenv("GMS_TTS_RESPONSE_FORMAT", "wav"),
            gms_temperature=_env_float("GMS_TEMPERATURE", 0.2),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
            elevenlabs_base_url=os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io"),
            elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb"),
            elevenlabs_model_id=os.getenv("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5"),
            elevenlabs_output_format=os.getenv("ELEVENLABS_OUTPUT_FORMAT", "pcm_24000"),
            elevenlabs_stability=_env_float("ELEVENLABS_STABILITY", 0.45),
            elevenlabs_similarity_boost=_env_float("ELEVENLABS_SIMILARITY_BOOST", 0.8),
            elevenlabs_style=_env_float("ELEVENLABS_STYLE", 0.0),
            elevenlabs_use_speaker_boost=_env_bool("ELEVENLABS_USE_SPEAKER_BOOST", True),
            elevenlabs_timeout_seconds=_env_float("ELEVENLABS_TIMEOUT_SECONDS", 30.0),
            vector_backend=os.getenv("QNA_VECTOR_BACKEND", "local"),
            retrieval_mode=os.getenv("QNA_RETRIEVAL_MODE", "hybrid"),
            vector_index_path=Path(
                os.getenv("QNA_VECTOR_INDEX_PATH", str(PROJECT_ROOT / "var" / "vector-index.json"))
            ),
            qdrant_url=os.getenv("QDRANT_URL", ""),
            qdrant_api_key=os.getenv("QDRANT_API_KEY", ""),
            qdrant_collection=os.getenv("QDRANT_COLLECTION", "boardgame_rules"),
            qdrant_timeout_seconds=_env_float("QDRANT_TIMEOUT_SECONDS", 30.0),
            llm_streaming=_env_bool("QNA_LLM_STREAMING", True),
            stt_mode=os.getenv("QNA_STT_MODE", "microphone"),
            audio_file=os.getenv("QNA_AUDIO_FILE", ""),
            mic_start_delay_seconds=_env_float("QNA_MIC_START_DELAY_SECONDS", 0.5),
            record_seconds=_env_float("QNA_RECORD_SECONDS", 4.0),
            record_min_seconds=_env_float("QNA_RECORD_MIN_SECONDS", 2.0),
            record_sample_rate=_env_int("QNA_RECORD_SAMPLE_RATE", 16000),
            record_channels=_env_int("QNA_RECORD_CHANNELS", 1),
            input_device=os.getenv("QNA_INPUT_DEVICE", ""),
            record_silence_seconds=_env_float("QNA_RECORD_SILENCE_SECONDS", 0.8),
            record_silence_threshold=_env_int("QNA_RECORD_SILENCE_THRESHOLD", 500),
            record_noise_seconds=_env_float("QNA_RECORD_NOISE_SECONDS", 0.35),
            record_threshold_multiplier=_env_float("QNA_RECORD_THRESHOLD_MULTIPLIER", 2.5),
            tts_mode=os.getenv("QNA_TTS_MODE", "gms"),
            tts_output_dir=Path(os.getenv("QNA_TTS_OUTPUT_DIR", str(PROJECT_ROOT / "var" / "audio"))),
            tts_play_audio=_env_bool("QNA_TTS_PLAY_AUDIO", True),
            tts_streaming=_env_bool("QNA_TTS_STREAMING", False),
            ready_sound_enabled=_env_bool("QNA_READY_SOUND_ENABLED", True),
            ready_sound_frequency=_env_int("QNA_READY_SOUND_FREQUENCY", 880),
            ready_sound_duration_seconds=_env_float("QNA_READY_SOUND_DURATION_SECONDS", 0.18),
            ready_sound_volume=_env_float("QNA_READY_SOUND_VOLUME", 0.22),
            ready_sound_output_device=os.getenv("QNA_READY_SOUND_OUTPUT_DEVICE", ""),
        )

    @property
    def broker_url(self) -> str:
        return f"tcp://{self.host}:{self.port}"


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer: {raw_value}") from exc


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number: {raw_value}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    return raw_value.lower() in {"1", "true", "yes", "y", "on"}


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""
