#!/usr/bin/env python3

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_server import MockWorkflow  # noqa: E402


class MockWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = MockWorkflow("rpi-01", 1, 2)
        self.card_topic = "/cabinet/rpi-01/card"
        self.return_status_topic = "/cabinet/rpi-01/1/status"
        self.receive_status_topic = "/cabinet/rpi-01/2/status"

    def send(self, topic: str, payload: dict, now: float = 10.0):
        return self.workflow.handle_message(topic, json.dumps(payload), now)

    def test_return_then_delayed_receive_then_complete(self) -> None:
        publications = self.send(
            self.card_topic,
            {"transactionId": "tx-1", "cardUid": "A1B2C3D4"},
        )
        self.assertEqual("/cabinet/rpi-01/1/open", publications[0].topic)
        self.assertEqual(
            {"transactionId": "tx-1", "step": 1, "mode": "return"},
            publications[0].payload,
        )

        self.assertEqual(
            [],
            self.send(
                self.return_status_topic,
                {"transactionId": "tx-1", "step": 1, "status": "closed", "mode": "return"},
                now=20.0,
            ),
        )
        self.assertEqual([], self.workflow.poll(20.999))
        publications = self.workflow.poll(21.0)
        self.assertEqual(
            {"transactionId": "tx-1", "step": 2, "mode": "receive"},
            publications[0].payload,
        )
        self.assertEqual("/cabinet/rpi-01/2/open", publications[0].topic)

        publications = self.send(
            self.receive_status_topic,
            {"transactionId": "tx-1", "step": 2, "status": "closed", "mode": "receive"},
        )
        self.assertEqual("/cabinet/rpi-01/complete", publications[0].topic)
        self.assertEqual({"transactionId": "tx-1"}, publications[0].payload)
        self.assertEqual("idle", self.workflow.state)

    def test_ignores_duplicate_unrelated_and_early_events(self) -> None:
        self.send(self.card_topic, {"transactionId": "tx-1", "cardUid": "A1"})
        self.assertEqual(
            [],
            self.send(self.card_topic, {"transactionId": "tx-2", "cardUid": "B2"}),
        )
        self.assertEqual(
            [],
            self.send(
                self.return_status_topic,
                {"transactionId": "wrong", "step": 1, "status": "closed"},
            ),
        )
        self.assertEqual(
            [],
            self.send(
                self.receive_status_topic,
                {"transactionId": "tx-1", "step": 2, "status": "closed"},
            ),
        )
        self.assertEqual("returning", self.workflow.state)

    def test_rejects_bad_card_payload(self) -> None:
        with self.assertRaises(ValueError):
            self.send(self.card_topic, {"transactionId": "tx-1"})

    def test_wrong_cabinet_status_does_not_advance(self) -> None:
        self.send(self.card_topic, {"transactionId": "tx-1", "cardUid": "A1"})
        self.assertEqual(
            [],
            self.send(
                self.receive_status_topic,
                {"transactionId": "tx-1", "step": 1, "status": "closed"},
            ),
        )
        self.assertEqual("returning", self.workflow.state)


if __name__ == "__main__":
    unittest.main()
