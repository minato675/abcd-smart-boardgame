from __future__ import annotations

import asyncio
import io
import json
import os
import pty
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout

import cr100emur
from cr100emur.cli import main as cli_main


FRAME = b"\x02" + b"680069DD2B" + b"\r\n\x03"


class CardTests(unittest.TestCase):
    def test_from_hex_normalizes_and_converts(self) -> None:
        card = cr100emur.Card.from_hex("680069dd2b")
        self.assertEqual(card.hex, "680069DD2B")
        self.assertEqual(card.uid, bytes.fromhex("680069DD2B"))
        self.assertEqual(card.value, 446_683_536_683)

    def test_invalid_hex_raises(self) -> None:
        with self.assertRaises(cr100emur.CR100Error):
            cr100emur.Card.from_hex("not-a-uid")


class ParserTests(unittest.TestCase):
    def test_one_byte_fragments(self) -> None:
        parser = cr100emur.Parser()
        cards: list[cr100emur.Card] = []
        for byte in FRAME:
            cards.extend(parser.feed(bytes([byte])))
        self.assertEqual([card.hex for card in cards], ["680069DD2B"])

    def test_multiple_frames(self) -> None:
        parser = cr100emur.Parser()
        cards = parser.feed(b"0000000001\r\nABCDEF1234\r\n")
        self.assertEqual(
            [card.hex for card in cards], ["0000000001", "ABCDEF1234"]
        )


class ReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.master, self.slave = pty.openpty()
        self.slave_path = os.ttyname(self.slave)

    def tearDown(self) -> None:
        os.close(self.slave)
        os.close(self.master)

    def test_context_manager_read_and_timeout(self) -> None:
        with cr100emur.Reader(self.slave_path) as reader:
            self.assertEqual(reader.device_path, self.slave_path)
            self.assertGreaterEqual(reader.fileno(), 0)
            os.write(self.master, FRAME)
            card = reader.read(timeout=0.5)
            self.assertIsNotNone(card)
            assert card is not None
            self.assertEqual(card.hex, "680069DD2B")
            self.assertIsNone(reader.read(timeout=0.01))
        self.assertTrue(reader.closed)

    def test_raw_read(self) -> None:
        with cr100emur.Reader(self.slave_path) as reader:
            os.write(self.master, FRAME)
            self.assertEqual(reader.read_raw(timeout=0.5), FRAME)
            self.assertIsNone(reader.read_raw(timeout=0))

    def test_unsupported_baud(self) -> None:
        with self.assertRaises(cr100emur.UnsupportedBaudError):
            cr100emur.Reader(self.slave_path, baud=12345)

    def test_json_cli(self) -> None:
        output = io.StringIO()
        errors = io.StringIO()
        writer = threading.Timer(0.02, os.write, args=(self.master, FRAME))
        writer.start()
        try:
            with redirect_stdout(output), redirect_stderr(errors):
                result = cli_main(
                    [
                        "--device",
                        self.slave_path,
                        "--count",
                        "1",
                        "--format",
                        "json",
                        "--timeout",
                        "0.5",
                    ]
                )
        finally:
            writer.join()
        self.assertEqual(result, 0, errors.getvalue())
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "uid": "680069DD2B",
                "value": 446_683_536_683,
                "bytes": [104, 0, 105, 221, 43],
            },
        )


class AsyncReaderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.master, self.slave = pty.openpty()
        self.slave_path = os.ttyname(self.slave)

    def tearDown(self) -> None:
        os.close(self.slave)
        os.close(self.master)

    async def test_readiness_callback_and_async_read(self) -> None:
        callbacks: list[str] = []

        async with cr100emur.AsyncReader(
            self.slave_path,
            on_card=lambda card: callbacks.append(card.hex),
        ) as reader:
            self.assertGreaterEqual(reader.fileno(), 0)
            os.write(self.master, FRAME)
            card = await asyncio.wait_for(reader.read(), timeout=1.0)
            self.assertEqual(card.hex, "680069DD2B")
            self.assertEqual(callbacks, ["680069DD2B"])

        self.assertTrue(reader.closed)

    async def test_async_callback_and_multiple_cards(self) -> None:
        callback_cards: list[str] = []
        callback_finished = asyncio.Event()

        async def on_card(card: cr100emur.Card) -> None:
            callback_cards.append(card.hex)
            if len(callback_cards) == 2:
                callback_finished.set()

        reader = cr100emur.AsyncReader(self.slave_path, on_card=on_card)
        reader.start()
        try:
            os.write(self.master, FRAME + FRAME)
            cards = [
                await asyncio.wait_for(reader.read(), timeout=1.0),
                await asyncio.wait_for(reader.read(), timeout=1.0),
            ]
            await asyncio.wait_for(callback_finished.wait(), timeout=1.0)
        finally:
            reader.close()

        self.assertEqual(
            [card.hex for card in cards],
            ["680069DD2B", "680069DD2B"],
        )
        self.assertEqual(callback_cards, ["680069DD2B", "680069DD2B"])


if __name__ == "__main__":
    unittest.main()
