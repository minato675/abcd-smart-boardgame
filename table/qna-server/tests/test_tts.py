from __future__ import annotations

import unittest
from pathlib import Path

from qna_server.tts import (
    ElevenLabsSpeechSynthesizer,
    GmsSpeechSynthesizer,
    build_speech_synthesizer,
    normalize_tts_text,
)


class FakeTtsClient:
    def synthesize_speech(self, text: str) -> bytes:
        return b"RIFF\x24\x00\x00\x00WAVEfmt "

    def stream_speech(self, text: str):
        yield b"\x00\x00\x01\x00"


class TtsTextNormalizeTest(unittest.TestCase):
    def test_tile_numbers_are_spoken_as_korean_numbers(self) -> None:
        text = normalize_tts_text("13 뒤에 숫자를 붙일 수 없습니다. 숫자 1은 가장 낮은 숫자입니다.")

        self.assertIn("십삼 뒤에", text)
        self.assertIn("일은", text)

    def test_player_count_and_score_are_spoken_naturally(self) -> None:
        text = normalize_tts_text("2~4명은 처음에 30점 이상을 등록해야 합니다.")

        self.assertIn("두 명에서 네 명", text)
        self.assertIn("삼십 점", text)

    def test_count_units_are_spoken_as_native_korean_numbers(self) -> None:
        text = normalize_tts_text("과일이 6개일 때는 종을 치면 안 되고, 카드 5장을 가져갑니다.")

        self.assertIn("여섯 개", text)
        self.assertIn("다섯 장", text)

    def test_live_pcm_streaming_disables_prefetch(self) -> None:
        synthesizer = GmsSpeechSynthesizer(
            client=FakeTtsClient(),
            output_dir=Path("var/audio"),
            play_audio=True,
            stream_audio=True,
            response_format="pcm",
        )

        self.assertFalse(synthesizer.supports_prefetch)

    def test_elevenlabs_mode_builds_pcm_streaming_synthesizer(self) -> None:
        synthesizer = build_speech_synthesizer(
            mode="elevenlabs",
            client=FakeTtsClient(),
            output_dir=Path("var/audio"),
            play_audio=True,
            stream_audio=True,
            response_format="pcm",
            elevenlabs_api_key="test-key",
            elevenlabs_voice_id="voice-id",
        )

        self.assertIsInstance(synthesizer, ElevenLabsSpeechSynthesizer)
        self.assertFalse(synthesizer.supports_prefetch)


if __name__ == "__main__":
    unittest.main()
