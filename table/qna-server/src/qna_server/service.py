from __future__ import annotations

import logging
import time
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from queue import Queue
from threading import Lock, Thread
from typing import Protocol

from .engine import Answer
from .payloads import (
    QnaReadyPayload,
    QnaResultPayload,
    QnaStartPayload,
    parse_qna_start,
    to_json,
)
from .audio_cue import ReadyCue
from .topics import qna_ready_topic, qna_result_topic, qna_thinking_topic, wake_start_listen_topic
from .tts import SpeechSynthesizer


class MqttPublisher(Protocol):
    def publish(self, topic: str, payload: str, qos: int) -> None:
        """Publish one MQTT message."""


class DirectAnswerer(Protocol):
    def answer(self, start: QnaStartPayload, on_recording_done=None) -> Answer:
        """Answer one QnA exchange directly from the start payload and microphone audio."""


@dataclass(frozen=True)
class PublishedMessage:
    topic: str
    payload: str
    qos: int


class InMemoryPublisher:
    def __init__(self) -> None:
        self.messages: list[PublishedMessage] = []

    def publish(self, topic: str, payload: str, qos: int) -> None:
        self.messages.append(PublishedMessage(topic=topic, payload=payload, qos=qos))


@dataclass(frozen=True)
class QnaExchange:
    start: QnaStartPayload
    question: str
    answer: str


class QnaService:
    def __init__(
        self,
        publisher: MqttPublisher,
        direct_answerer: DirectAnswerer,
        speech_synthesizer: SpeechSynthesizer,
        qos: int = 1,
        publish_wake_start: bool = True,
        ready_cue: ReadyCue | None = None,
        mic_start_delay_seconds: float = 0.0,
    ) -> None:
        if mic_start_delay_seconds < 0:
            raise ValueError("mic_start_delay_seconds must be greater than or equal to 0")
        self._publisher = publisher
        self._direct_answerer = direct_answerer
        self._speech_synthesizer = speech_synthesizer
        self._qos = qos
        self._publish_wake_start = publish_wake_start
        self._ready_cue = ready_cue
        self._mic_start_delay_seconds = mic_start_delay_seconds
        self._transaction_lock = Lock()
        self._seen_transactions: OrderedDict[tuple[str, str], float] = OrderedDict()
        self._max_seen_transactions = 1024

    def handle_start(self, topic: str, payload: str | bytes) -> QnaExchange | None:
        try:
            start = parse_qna_start(topic, payload)
        except Exception:
            logging.exception("Cannot parse qna/start message: topic=%s payload=%r", topic, payload)
            return None

        if not self._mark_transaction_seen(start):
            logging.info(
                "Duplicate qna/start ignored: roomNumber=%s transactionId=%s",
                start.room_number,
                start.transaction_id,
            )
            return None

        logging.info(
            "QnA start: roomNumber=%s transactionId=%s boardgameName=%s players=%s",
            start.room_number,
            start.transaction_id,
            start.boardgame_name,
            start.players,
        )

        started_at = time.perf_counter()
        thinking_published = False

        def publish_thinking_once() -> None:
            nonlocal thinking_published
            if thinking_published:
                return
            self._publish_thinking(start.room_number)
            thinking_published = True

        try:
            self._wait_before_microphone(started_at)
            self._publish_ready(start.transaction_id, start.room_number)
            self._play_ready_cue()
            tts_pipeline = _SentenceTtsPipeline(
                self._speech_synthesizer,
                start.room_number,
                started_at,
            )
            try:
                answer = self._direct_answerer.answer(
                    start,
                    publish_thinking_once,
                )
                question = answer.question
                logging.info("QnA direct question: %s elapsed=%.3fs", question, time.perf_counter() - started_at)
                _print_terminal_box(
                    "인식된 질문",
                    [
                        f"roomNumber={start.room_number}",
                        f"transactionId={start.transaction_id}",
                        question,
                    ],
                )
            except Exception:
                publish_thinking_once()
                tts_pipeline.cancel()
                raise
            logging.info("QnA answer: %s elapsed=%.3fs", answer.text, time.perf_counter() - started_at)
            self._publish_result(start, answer.question, answer.text)
            logging.info("QnA result published: roomNumber=%s elapsed=%.3fs", start.room_number, time.perf_counter() - started_at)
            if answer.spoken_sentences == 0:
                tts_pipeline.submit(answer.text)
            tts_pipeline.close()
        except Exception as exc:
            logging.exception("QnA pipeline failed: roomNumber=%s", start.room_number)
            message = "QnA 서버 에러가 발생했습니다. 잠시 후 다시 시도해 주세요."
            self._publish_ready_error(start.transaction_id, start.room_number, str(exc))
            self._publish_result(start, question if "question" in locals() else "", message)
            return QnaExchange(start=start, question=question if "question" in locals() else "", answer=message)
        finally:
            self._restart_wake_word(start.room_number)

        return QnaExchange(start=start, question=answer.question, answer=answer.text)

    def _mark_transaction_seen(self, start: QnaStartPayload) -> bool:
        key = (start.room_number, start.transaction_id)
        with self._transaction_lock:
            if key in self._seen_transactions:
                self._seen_transactions.move_to_end(key)
                return False
            self._seen_transactions[key] = time.monotonic()
            while len(self._seen_transactions) > self._max_seen_transactions:
                self._seen_transactions.popitem(last=False)
            return True

    def _publish_ready(self, transaction_id: str, room_number: str) -> None:
        payload = QnaReadyPayload(transactionId=transaction_id, status="ready")
        topic = qna_ready_topic(room_number)
        self._publisher.publish(topic, to_json(payload), self._qos)
        logging.info(
            "QnA ready published: roomNumber=%s transactionId=%s status=ready topic=%s",
            room_number,
            transaction_id,
            topic,
        )

    def _play_ready_cue(self) -> None:
        if self._ready_cue is None:
            return
        try:
            self._ready_cue.play_ready()
        except Exception:
            logging.exception("Ready cue failed; continuing QnA pipeline.")

    def _wait_before_microphone(self, started_at: float) -> None:
        if self._mic_start_delay_seconds <= 0:
            return
        logging.info(
            "Waiting before microphone capture: delay=%.3fs elapsed=%.3fs",
            self._mic_start_delay_seconds,
            time.perf_counter() - started_at,
        )
        time.sleep(self._mic_start_delay_seconds)

    def _publish_ready_error(self, transaction_id: str, room_number: str, message: str) -> None:
        payload = QnaReadyPayload(transactionId=transaction_id, status="error", msg=message)
        topic = qna_ready_topic(room_number)
        self._publisher.publish(topic, to_json(payload), self._qos)
        logging.info(
            "QnA ready published: roomNumber=%s transactionId=%s status=error topic=%s msg=%s",
            room_number,
            transaction_id,
            topic,
            message,
        )

    def _publish_result(self, start: QnaStartPayload, question: str, answer: str) -> None:
        payload = QnaResultPayload(
            transactionId=start.transaction_id,
            req=question,
            res=answer,
        )
        self._publisher.publish(qna_result_topic(start.room_number), to_json(payload), self._qos)

    def _publish_thinking(self, room_number: str) -> None:
        topic = qna_thinking_topic(room_number)
        try:
            self._publisher.publish(topic, "{}", self._qos)
            logging.info("QnA thinking published: roomNumber=%s topic=%s payload={}", room_number, topic)
        except Exception:
            logging.exception("QnA thinking publish failed; continuing QnA pipeline: topic=%s", topic)

    def _restart_wake_word(self, room_number: str) -> None:
        if self._publish_wake_start:
            self._publisher.publish(wake_start_listen_topic(room_number), "{}", self._qos)


class _SentenceTtsPipeline:
    def __init__(
        self,
        speech_synthesizer: SpeechSynthesizer,
        room_number: str,
        started_at: float,
    ) -> None:
        self._speech_synthesizer = speech_synthesizer
        self._room_number = room_number
        self._started_at = started_at
        self._can_prefetch = (
            hasattr(speech_synthesizer, "prepare")
            and hasattr(speech_synthesizer, "play")
            and getattr(speech_synthesizer, "supports_prefetch", True)
        )
        self._executor = ThreadPoolExecutor(max_workers=2 if self._can_prefetch else 1)
        self._queue: Queue[Future | None] = Queue()
        self._player = Thread(target=self._play_loop, daemon=True)
        self._player.start()

    def submit(self, sentence: str) -> None:
        sentence = sentence.strip()
        if not sentence:
            return
        logging.info(
            "QnA sentence ready for TTS: %s elapsed=%.3fs",
            sentence,
            time.perf_counter() - self._started_at,
        )
        if self._can_prefetch:
            future = self._executor.submit(getattr(self._speech_synthesizer, "prepare"), sentence)
        else:
            future = self._executor.submit(self._speech_synthesizer.speak, sentence)
        self._queue.put(future)

    def close(self) -> None:
        self._queue.put(None)
        self._player.join()
        self._executor.shutdown(wait=True)
        logging.info(
            "QnA TTS completed: roomNumber=%s elapsed=%.3fs",
            self._room_number,
            time.perf_counter() - self._started_at,
        )

    def cancel(self) -> None:
        self._queue.put(None)
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _play_loop(self) -> None:
        while True:
            future = self._queue.get()
            if future is None:
                return
            try:
                speech = future.result()
                if self._can_prefetch:
                    getattr(self._speech_synthesizer, "play")(speech)
            except Exception:
                logging.exception(
                    "QnA TTS failed after result published: roomNumber=%s",
                    self._room_number,
                )


def _print_terminal_box(title: str, lines: list[str]) -> None:
    border = "=" * 56
    body = "\n".join(lines)
    print(f"\n{border}\n{title}\n{body}\n{border}\n", flush=True)
