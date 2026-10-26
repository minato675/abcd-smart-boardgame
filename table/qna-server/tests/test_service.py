from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from qna_server.engine import Answer
from qna_server.payloads import to_json
from qna_server.service import InMemoryPublisher, QnaService


class FixedDirectAnswerer:
    def answer(self, start, on_recording_done=None) -> Answer:
        if on_recording_done is not None:
            on_recording_done()
        return Answer(
            question="루미큐브에서 조커는 어떻게 써?",
            text="조커는 필요한 숫자와 색을 대신할 수 있습니다.",
        )


class FailingDirectAnswerer:
    def answer(self, start, on_recording_done=None) -> Answer:
        raise RuntimeError("microphone unavailable")


class CountingDirectAnswerer:
    def __init__(self) -> None:
        self.call_count = 0

    def answer(self, start, on_recording_done=None) -> Answer:
        self.call_count += 1
        if on_recording_done is not None:
            on_recording_done()
        return Answer(
            question="할리갈리에서 과일 5개면 종 쳐도 돼?",
            text="같은 과일이 정확히 5개일 때만 종을 칠 수 있습니다.",
        )


class CapturingSynthesizer:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


class CapturingReadyCue:
    def __init__(self) -> None:
        self.play_count = 0

    def play_ready(self) -> None:
        self.play_count += 1


class OrderedDirectAnswerer:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def answer(self, start, on_recording_done=None) -> Answer:
        self._events.append("answer")
        if on_recording_done is not None:
            on_recording_done()
        return Answer(
            question="루미큐브에서 조커는 어떻게 써?",
            text="조커는 필요한 숫자와 색을 대신할 수 있습니다.",
        )


class OrderedReadyCue:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def play_ready(self) -> None:
        self._events.append("ready")


class QnaServiceTest(unittest.TestCase):
    def test_start_publishes_ready_and_result(self) -> None:
        publisher = InMemoryPublisher()
        ready_cue = CapturingReadyCue()
        service = QnaService(
            publisher=publisher,
            direct_answerer=FixedDirectAnswerer(),
            speech_synthesizer=CapturingSynthesizer(),
            qos=1,
            ready_cue=ready_cue,
        )

        exchange = service.handle_start(
            "/room/1/qna/start",
            to_json(
                {
                    "transactionId": "123e4567-e89b-12d3-a456-556642440000",
                    "boardgameName": "루미큐브",
                }
            ),
        )

        self.assertIsNotNone(exchange)
        self.assertEqual([message.topic for message in publisher.messages], [
            "/room/1/qna/ready",
            "/room/1/qna/thinking",
            "/room/1/qna/res",
            "/room/1/wake/start-listen",
        ])

        ready = json.loads(publisher.messages[0].payload)
        thinking = json.loads(publisher.messages[1].payload)
        result = json.loads(publisher.messages[2].payload)

        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["transactionId"], "123e4567-e89b-12d3-a456-556642440000")
        self.assertEqual(thinking, {})
        self.assertEqual(result["req"], "루미큐브에서 조커는 어떻게 써?")
        self.assertIn("조커", result["res"])
        self.assertEqual(ready_cue.play_count, 1)

    def test_pipeline_failure_publishes_error_result_and_restarts_wake_word(self) -> None:
        publisher = InMemoryPublisher()
        service = QnaService(
            publisher=publisher,
            direct_answerer=FailingDirectAnswerer(),
            speech_synthesizer=CapturingSynthesizer(),
            qos=1,
        )

        exchange = service.handle_start(
            "/room/1/qna/start",
            to_json(
                {
                    "transactionId": "123e4567-e89b-12d3-a456-556642440000",
                    "boardgameName": "루미큐브",
                }
            ),
        )

        self.assertIsNotNone(exchange)
        self.assertEqual([message.topic for message in publisher.messages], [
            "/room/1/qna/ready",
            "/room/1/qna/thinking",
            "/room/1/qna/ready",
            "/room/1/qna/res",
            "/room/1/wake/start-listen",
        ])

        thinking = json.loads(publisher.messages[1].payload)
        ready_error = json.loads(publisher.messages[2].payload)
        result = json.loads(publisher.messages[3].payload)

        self.assertEqual(thinking, {})
        self.assertEqual(ready_error["status"], "error")
        self.assertEqual(ready_error["msg"], "microphone unavailable")
        self.assertEqual(result["req"], "")
        self.assertIn("QnA 서버 에러", result["res"])

    def test_start_uses_direct_answerer_and_publishes_result(self) -> None:
        publisher = InMemoryPublisher()
        service = QnaService(
            publisher=publisher,
            direct_answerer=FixedDirectAnswerer(),
            speech_synthesizer=CapturingSynthesizer(),
            qos=1,
        )

        exchange = service.handle_start(
            "/room/1/qna/start",
            to_json(
                {
                    "transactionId": "123e4567-e89b-12d3-a456-556642440000",
                    "boardgameName": "루미큐브",
                }
            ),
        )

        self.assertIsNotNone(exchange)
        result = json.loads(publisher.messages[2].payload)
        self.assertEqual(result["req"], "루미큐브에서 조커는 어떻게 써?")
        self.assertEqual(result["res"], "조커는 필요한 숫자와 색을 대신할 수 있습니다.")

    def test_duplicate_qos1_start_is_ignored_by_transaction_id(self) -> None:
        publisher = InMemoryPublisher()
        answerer = CountingDirectAnswerer()
        service = QnaService(
            publisher=publisher,
            direct_answerer=answerer,
            speech_synthesizer=CapturingSynthesizer(),
            qos=1,
        )
        payload = to_json(
            {
                "transactionId": "123e4567-e89b-12d3-a456-556642440000",
                "boardgameName": "할리갈리",
            }
        )

        first = service.handle_start("/room/1/qna/start", payload)
        second = service.handle_start("/room/1/qna/start", payload)

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(answerer.call_count, 1)
        self.assertEqual([message.topic for message in publisher.messages], [
            "/room/1/qna/ready",
            "/room/1/qna/thinking",
            "/room/1/qna/res",
            "/room/1/wake/start-listen",
        ])

    def test_mic_start_delay_runs_before_ready_cue_and_recognition(self) -> None:
        events: list[str] = []
        publisher = InMemoryPublisher()
        service = QnaService(
            publisher=publisher,
            direct_answerer=OrderedDirectAnswerer(events),
            speech_synthesizer=CapturingSynthesizer(),
            qos=1,
            ready_cue=OrderedReadyCue(events),
            mic_start_delay_seconds=0.5,
        )

        with patch("qna_server.service.time.sleep", side_effect=lambda seconds: events.append(f"sleep:{seconds}")):
            service.handle_start(
                "/room/1/qna/start",
                to_json(
                    {
                        "transactionId": "123e4567-e89b-12d3-a456-556642440000",
                        "boardgameName": "루미큐브",
                    }
                ),
            )

        self.assertEqual(events, ["sleep:0.5", "ready", "answer"])


if __name__ == "__main__":
    unittest.main()
