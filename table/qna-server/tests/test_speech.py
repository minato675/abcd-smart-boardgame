from __future__ import annotations

import unittest
from array import array

from qna_server.speech import (
    _looks_like_invalid_question_transcript,
    _pcm_int16_to_mono,
    _resolve_input_stream_settings,
    _suppress_noise_pcm_int16,
)


class SpeechTest(unittest.TestCase):
    def test_short_finish_transcript_is_unusable(self) -> None:
        self.assertTrue(_looks_like_invalid_question_transcript("끝"))
        self.assertTrue(_looks_like_invalid_question_transcript("네"))
        self.assertTrue(_looks_like_invalid_question_transcript("안녕!"))

    def test_rule_question_is_usable(self) -> None:
        self.assertFalse(_looks_like_invalid_question_transcript("과일 6개일 때 종 쳐도 돼?"))

    def test_stt_hallucination_phrase_is_unusable(self) -> None:
        transcript = "네, 알겠습니다. 오케이, 리눅스 뺨파리 이어서 네, 종이를 틀어볼게요."

        self.assertTrue(_looks_like_invalid_question_transcript(transcript))

    def test_noise_suppression_trims_low_level_edges(self) -> None:
        samples = array("h", [20] * 16000 + [2200] * 8000 + [20] * 16000)

        enhanced, frame_count = _suppress_noise_pcm_int16(samples.tobytes(), 16000, 500)

        self.assertLess(frame_count, len(samples))
        self.assertGreater(frame_count, 8000)
        self.assertLess(len(enhanced), len(samples.tobytes()))

    def test_stereo_pcm_is_mixed_to_mono(self) -> None:
        samples = array("h", [1000, -1000, 2000, 0])

        mono = array("h")
        mono.frombytes(_pcm_int16_to_mono(samples.tobytes(), 2))

        self.assertEqual(list(mono), [0, 1000])

    def test_invalid_configured_input_device_falls_back_to_default(self) -> None:
        class FakeSoundDevice:
            def query_devices(self, device=None, kind=None):
                if kind == "input":
                    return {"max_input_channels": 1}
                raise RuntimeError("device not found")

        device, channels, label = _resolve_input_stream_settings(FakeSoundDevice(), "27", 2)

        self.assertIsNone(device)
        self.assertEqual(channels, 1)
        self.assertEqual(label, "<default>")


if __name__ == "__main__":
    unittest.main()
