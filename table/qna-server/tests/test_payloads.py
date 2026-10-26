from __future__ import annotations

import json
import unittest

from qna_server.payloads import parse_qna_start


class QnaStartPayloadTest(unittest.TestCase):
    def test_parse_spec_payload(self) -> None:
        payload = json.dumps(
            {
                "transactionId": "123e4567-e89b-12d3-a456-556642440000",
                "boardgameName": "루미큐브",
                "players": 4,
            },
            ensure_ascii=False,
        )

        result = parse_qna_start("/room/1/qna/start", payload)

        self.assertEqual(result.room_number, "1")
        self.assertEqual(result.transaction_id, "123e4567-e89b-12d3-a456-556642440000")
        self.assertEqual(result.boardgame_name, "루미큐브")
        self.assertEqual(result.players, 4)

    def test_players_is_optional_for_current_spring_payload(self) -> None:
        payload = json.dumps(
            {
                "transactionId": "123e4567-e89b-12d3-a456-556642440000",
                "boardgameName": "루미큐브",
            },
            ensure_ascii=False,
        )

        result = parse_qna_start("/room/1/qna/start", payload)

        self.assertIsNone(result.players)

    def test_parse_spring_camel_case_board_game_name(self) -> None:
        payload = json.dumps(
            {
                "transactionId": "123e4567-e89b-12d3-a456-556642440000",
                "boardGameName": "루미큐브",
            },
            ensure_ascii=False,
        )

        result = parse_qna_start("/room/room-01/qna/start", payload)

        self.assertEqual(result.room_number, "room-01")
        self.assertEqual(result.boardgame_name, "루미큐브")

    def test_invalid_topic_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_qna_start("/room/1/qna/res", "{}")


if __name__ == "__main__":
    unittest.main()

