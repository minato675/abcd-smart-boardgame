from __future__ import annotations

import argparse
import json
import logging
import time

from .audio_cue import build_ready_cue
from .config import Settings
from .direct import GeminiDirectAnswerer
from .engine import Answer
from .gms_client import GmsAuth, GmsClient, GmsEndpoints, GmsModels
from .knowledge import RuleKnowledgeBase
from .payloads import to_json
from .service import InMemoryPublisher, QnaService
from .tts import LoggingSpeechSynthesizer, build_speech_synthesizer
from .vector_store import QdrantHttpClient, QdrantRuleVectorStore, RuleVectorStore


class SelfTestDirectAnswerer:
    def answer(self, start, on_recording_done=None) -> Answer:
        if on_recording_done is not None:
            on_recording_done()
        prefix = f"{start.players}명 기준으로 보면, " if start.players is not None else ""
        return Answer(
            question="루미큐브에서 조커는 어떻게 써?",
            text=(
                f"{prefix}조커는 필요한 숫자와 색을 대신할 수 있고, "
                "회수한 조커는 같은 턴에 바로 새 유효 조합에 사용해야 합니다."
            ),
        )


def build_gms_client(settings: Settings) -> GmsClient:
    return GmsClient(
        auth=GmsAuth(
            api_key=settings.gms_api_key,
            header=settings.gms_auth_header,
            scheme=settings.gms_auth_scheme,
        ),
        endpoints=GmsEndpoints(
            base_url=settings.gms_base_url,
            chat=settings.gms_chat_endpoint,
            stt=settings.gms_stt_endpoint,
            tts=settings.gms_tts_endpoint,
            embeddings=settings.gms_embedding_endpoint,
            models=settings.gms_models_endpoint,
            gemini_audio_base_url=settings.gms_gemini_audio_base_url,
            gemini_audio_endpoint=settings.gms_gemini_audio_endpoint,
            gemini_audio_request_style=settings.gms_gemini_audio_request_style,
        ),
        models=GmsModels(
            text_model=settings.gms_text_model,
            stt_model=settings.gms_stt_model,
            tts_model=settings.gms_tts_model,
            embedding_model=settings.gms_embedding_model,
            tts_voice=settings.gms_voice,
            tts_response_format=settings.gms_tts_response_format,
            temperature=settings.gms_temperature,
            gemini_audio_model=settings.gms_gemini_audio_model,
        ),
    )


def build_service(settings: Settings, publisher) -> QnaService:
    gms_client = build_gms_client(settings)
    knowledge_base = RuleKnowledgeBase.load(settings.rule_dir)
    logging.info("Rulebook loaded: chunks=%s ruleDir=%s", len(knowledge_base.chunks), settings.rule_dir)
    direct_answerer = GeminiDirectAnswerer(
        knowledge_base,
        gms_client,
        settings.record_seconds,
        settings.record_min_seconds,
        settings.record_sample_rate,
        settings.record_channels,
        settings.input_device,
        settings.record_silence_seconds,
        settings.record_silence_threshold,
        settings.record_noise_seconds,
        settings.record_threshold_multiplier,
    )
    speech_synthesizer = build_speech_synthesizer(
        settings.tts_mode,
        gms_client,
        settings.tts_output_dir,
        settings.tts_play_audio,
        settings.tts_streaming,
        settings.gms_tts_response_format,
        elevenlabs_api_key=settings.elevenlabs_api_key,
        elevenlabs_base_url=settings.elevenlabs_base_url,
        elevenlabs_voice_id=settings.elevenlabs_voice_id,
        elevenlabs_model_id=settings.elevenlabs_model_id,
        elevenlabs_output_format=settings.elevenlabs_output_format,
        elevenlabs_stability=settings.elevenlabs_stability,
        elevenlabs_similarity_boost=settings.elevenlabs_similarity_boost,
        elevenlabs_style=settings.elevenlabs_style,
        elevenlabs_use_speaker_boost=settings.elevenlabs_use_speaker_boost,
        elevenlabs_timeout_seconds=settings.elevenlabs_timeout_seconds,
    )
    ready_cue = build_ready_cue(
        settings.ready_sound_enabled,
        settings.ready_sound_frequency,
        settings.ready_sound_duration_seconds,
        settings.ready_sound_volume,
        settings.ready_sound_output_device,
    )
    return QnaService(
        publisher=publisher,
        direct_answerer=direct_answerer,
        speech_synthesizer=speech_synthesizer,
        qos=settings.qos,
        publish_wake_start=settings.publish_wake_start,
        ready_cue=ready_cue,
        mic_start_delay_seconds=settings.mic_start_delay_seconds,
    )


def build_vector_store(settings: Settings, knowledge_base: RuleKnowledgeBase, gms_client: GmsClient):
    backend = settings.vector_backend.lower()
    if backend == "local":
        return RuleVectorStore.load_or_build(
            knowledge_base,
            settings.vector_index_path,
            settings.gms_embedding_model,
            gms_client,
        )
    if backend == "qdrant":
        return QdrantRuleVectorStore.load_or_build(
            knowledge_base,
            settings.gms_embedding_model,
            gms_client,
            QdrantHttpClient(
                settings.qdrant_url,
                settings.qdrant_collection,
                api_key=settings.qdrant_api_key,
                timeout_seconds=settings.qdrant_timeout_seconds,
            ),
        )
    raise ValueError(f"Unsupported QNA_VECTOR_BACKEND: {settings.vector_backend}")


def run_self_test(settings: Settings) -> None:
    publisher = InMemoryPublisher()
    service = QnaService(
        publisher=publisher,
        direct_answerer=SelfTestDirectAnswerer(),
        speech_synthesizer=LoggingSpeechSynthesizer(),
        qos=settings.qos,
        publish_wake_start=settings.publish_wake_start,
    )
    service.handle_start(
        "/room/1/qna/start",
        to_json(
            {
                "transactionId": "123e4567-e89b-12d3-a456-556642440000",
                "boardgameName": "루미큐브",
                "players": 4,
            }
        ),
    )

    for message in publisher.messages:
        print(message.topic)
        print(json.dumps(json.loads(message.payload), ensure_ascii=False, indent=2))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Board-game QnA MQTT server")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run one local qna/start exchange without connecting to MQTT.",
    )
    parser.add_argument(
        "--list-gms-models",
        action="store_true",
        help="Print model IDs returned by the configured GMS models endpoint.",
    )
    parser.add_argument(
        "--check-tts-streaming",
        action="store_true",
        help="Check whether the configured GMS TTS endpoint streams audio chunks.",
    )
    parser.add_argument(
        "--build-vector-index",
        action="store_true",
        help="Build or refresh the local rulebook VectorDB index.",
    )
    args = parser.parse_args()

    settings = Settings.from_env()

    if args.self_test:
        run_self_test(settings)
        return

    if args.list_gms_models:
        data = build_gms_client(settings).list_models()
        model_ids = _extract_model_ids(data)
        if model_ids:
            print("GMS models:")
            for model_id in model_ids:
                print(f"- {model_id}")
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if args.check_tts_streaming:
        check_tts_streaming(build_gms_client(settings), settings.gms_tts_response_format)
        return

    if args.build_vector_index:
        knowledge_base = RuleKnowledgeBase.load(settings.rule_dir)
        vector_store = build_vector_store(settings, knowledge_base, build_gms_client(settings))
        print(f"VectorDB ready: backend={settings.vector_backend}")
        if settings.vector_backend.lower() == "local":
            print(f"path={settings.vector_index_path}")
        if settings.vector_backend.lower() == "qdrant":
            print(f"qdrantUrl={settings.qdrant_url}")
            print(f"collection={settings.qdrant_collection}")
        print(f"chunks={len(knowledge_base.chunks)}")
        print(f"mode={settings.retrieval_mode}")
        print(f"embeddingModel={settings.gms_embedding_model}")
        sample_chunks = vector_store.search("할리갈리", "과일 6개일 때 종 쳐도 돼?", limit=2)
        for chunk in sample_chunks:
            print(f"- {chunk.game_key}/{chunk.title}")
        return

    try:
        from .mqtt_client import MqttQnaApp
    except ImportError as exc:
        raise SystemExit(
            "paho-mqtt가 필요합니다. table/qna-server에서 `pip install -r requirements.txt`를 실행하세요."
        ) from exc

    app = MqttQnaApp(settings, build_service)
    app.run_forever()


def _extract_model_ids(data: dict) -> list[str]:
    raw_models = data.get("data")
    if not isinstance(raw_models, list):
        raw_models = data.get("models")
    if not isinstance(raw_models, list):
        return []

    model_ids: list[str] = []
    for item in raw_models:
        if isinstance(item, dict):
            model_id = item.get("id") or item.get("name") or item.get("model")
            if isinstance(model_id, str):
                model_ids.append(model_id)
        elif isinstance(item, str):
            model_ids.append(item)
    return model_ids


def check_tts_streaming(client: GmsClient, response_format: str) -> None:
    started_at = time.perf_counter()
    chunk_count = 0
    byte_count = 0
    first_chunk_at: float | None = None
    first_bytes = b""
    text = (
        "테스트 문장입니다. "
        "이 문장은 GMS TTS가 오디오를 한 번에 내려주는지, "
        "아니면 생성되는 즉시 여러 PCM 조각으로 내려주는지 확인하기 위한 문장입니다."
    )

    for chunk in client.stream_speech(text):
        now = time.perf_counter()
        if first_chunk_at is None:
            first_chunk_at = now
            first_bytes = chunk[:16]
        chunk_count += 1
        byte_count += len(chunk)

    elapsed = time.perf_counter() - started_at
    first_elapsed = (first_chunk_at - started_at) if first_chunk_at else None
    first_ratio = (first_elapsed / elapsed) if first_elapsed is not None and elapsed > 0 else None
    print(f"response_format={response_format}")
    print(f"chunks={chunk_count}")
    print(f"bytes={byte_count}")
    print(f"time_to_first_chunk={first_elapsed:.3f}s" if first_elapsed is not None else "time_to_first_chunk=<none>")
    print(f"elapsed={elapsed:.3f}s")
    print(f"first_chunk_ratio={first_ratio:.3f}" if first_ratio is not None else "first_chunk_ratio=<none>")
    print(f"first_bytes_hex={first_bytes.hex(' ')}")

    if chunk_count <= 1:
        print("result=not_streaming_or_buffered")
    elif response_format.lower() == "pcm" and first_elapsed is not None and first_elapsed < max(1.5, elapsed * 0.7):
        print("result=pcm_streaming_supported")
    elif response_format.lower() == "pcm":
        print("result=pcm_chunked_but_likely_buffered")
    else:
        print("result=http_chunked_but_not_live_pcm")


if __name__ == "__main__":
    main()
