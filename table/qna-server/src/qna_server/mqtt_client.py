from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from paho.mqtt import client as mqtt

from .config import Settings
from .service import MqttPublisher, QnaService


START_TOPIC_FILTER = "/room/+/qna/start"


class PahoPublisher:
    def __init__(self, client: mqtt.Client) -> None:
        self._client = client

    def publish(self, topic: str, payload: str, qos: int) -> None:
        info = self._client.publish(topic, payload=payload, qos=qos)
        if qos <= 0:
            return
        try:
            info.wait_for_publish(timeout=3.0)
            if not info.is_published():
                logging.warning("MQTT publish is not confirmed yet: topic=%s qos=%s", topic, qos)
        except TypeError:
            info.wait_for_publish()
        except Exception:
            logging.exception("MQTT publish confirmation failed: topic=%s qos=%s", topic, qos)


class MqttQnaApp:
    def __init__(self, settings: Settings, service_factory) -> None:
        self._settings = settings
        self._client = _create_client(settings.client_id)
        self._publisher = PahoPublisher(self._client)
        self._service: QnaService = service_factory(settings, self._publisher)
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="qna-worker")

        if settings.username:
            self._client.username_pw_set(settings.username, settings.password)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def run_forever(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        logging.info(
            "QnA settings: answerMode=gemini-direct micStartDelay=%.3f recordSeconds=%.3f minSeconds=%.3f silenceSeconds=%.3f "
            "sampleRate=%s channels=%s inputDevice=%s ruleContext=full-game-rulebook "
            "geminiAudioModel=%s geminiAudioStyle=%s "
            "ttsMode=%s ttsModel=%s elevenLabsModel=%s "
            "ttsStreaming=%s ttsFormat=%s elevenLabsFormat=%s readySound=%s readySoundOutputDevice=%s",
            self._settings.mic_start_delay_seconds,
            self._settings.record_seconds,
            self._settings.record_min_seconds,
            self._settings.record_silence_seconds,
            self._settings.record_sample_rate,
            self._settings.record_channels,
            self._settings.input_device or "<default>",
            self._settings.gms_gemini_audio_model,
            self._settings.gms_gemini_audio_request_style,
            self._settings.tts_mode,
            self._settings.gms_tts_model,
            self._settings.elevenlabs_model_id,
            self._settings.tts_streaming,
            self._settings.gms_tts_response_format,
            self._settings.elevenlabs_output_format,
            self._settings.ready_sound_enabled,
            self._settings.ready_sound_output_device or "<default>",
        )
        logging.info("Connecting to MQTT broker %s", self._settings.broker_url)
        self._client.connect(self._settings.host, self._settings.port, keepalive=60)
        try:
            self._client.loop_forever()
        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        logging.info("MQTT connected: %s", reason_code)
        client.subscribe(START_TOPIC_FILTER, qos=self._settings.qos)
        logging.info("Subscribed: %s", START_TOPIC_FILTER)

    def _on_message(self, client, userdata, message) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        logging.info("Received %s %s", message.topic, payload)
        self._executor.submit(self._handle_start_message, message.topic, payload)

    def _handle_start_message(self, topic: str, payload: str) -> None:
        try:
            self._service.handle_start(topic, payload)
        except Exception:
            logging.exception("Unhandled qna/start worker error: topic=%s payload=%r", topic, payload)


def _create_client(client_id: str) -> mqtt.Client:
    callback_api = getattr(mqtt, "CallbackAPIVersion", None)
    if callback_api is not None:
        return mqtt.Client(callback_api.VERSION2, client_id=client_id)
    return mqtt.Client(client_id=client_id)

