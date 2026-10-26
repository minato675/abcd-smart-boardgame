from __future__ import annotations

import unittest

from qna_server.gms_client import (
    GmsAuth,
    GmsClient,
    GmsEndpoints,
    GmsModels,
    _clean_gemini_transcript,
    _extract_gemini_audio_text,
    _looks_like_stt_prompt_echo,
    _parse_direct_audio_answer,
)


class GmsClientTest(unittest.TestCase):
    def test_stt_prompt_echo_is_rejected(self) -> None:
        self.assertTrue(_looks_like_stt_prompt_echo("사용자가 말한 질문만 한국어로 전사하세요."))
        self.assertTrue(_looks_like_stt_prompt_echo("보드게임 규칙 질문입니다."))

    def test_normal_question_is_not_prompt_echo(self) -> None:
        self.assertFalse(_looks_like_stt_prompt_echo("과일 6개일 때 종 쳐도 돼?"))

    def test_gemini_interactions_audio_request_uses_inline_audio(self) -> None:
        client = _make_gms_client("interactions")

        url, payload = client._gemini_audio_transcription_request(
            "전사해줘",
            "audio/wav",
            "YWJj",
        )

        self.assertEqual(url, "https://gms.test/gemini/v1beta/interactions")
        self.assertEqual(payload["model"], "gemini-2.5-flash")
        self.assertEqual(payload["input"][0]["type"], "text")
        self.assertEqual(payload["input"][1]["type"], "audio")
        self.assertEqual(payload["input"][1]["data"], "YWJj")
        self.assertEqual(payload["input"][1]["mime_type"], "audio/wav")

    def test_gemini_audio_uses_google_style_api_key_header(self) -> None:
        client = _make_gms_client("interactions", base_url="https://gms.test/generativelanguage.googleapis.com")

        self.assertEqual(client._gemini_audio_auth_headers(), {"x-goog-api-key": "test-key"})

    def test_gemini_audio_uses_default_auth_for_openai_compatible_gateway(self) -> None:
        client = _make_gms_client("openai-chat", base_url="https://gms.test/api.openai.com")

        self.assertEqual(client._gemini_audio_auth_headers(), {"Authorization": "Bearer test-key"})

    def test_gemini_generate_content_audio_request_uses_inline_data(self) -> None:
        client = _make_gms_client("generate-content")

        url, payload = client._gemini_audio_transcription_request(
            "전사해줘",
            "audio/wav",
            "YWJj",
        )

        self.assertEqual(url, "https://gms.test/gemini/v1beta/models/gemini-2.5-flash:generateContent")
        self.assertIn("system_instruction", payload)
        self.assertIn("contents", payload)
        inline_data = payload["contents"][0]["parts"][1]["inline_data"]
        self.assertEqual(inline_data["data"], "YWJj")
        self.assertEqual(inline_data["mime_type"], "audio/wav")

    def test_gemini_audio_text_is_extracted_from_candidates(self) -> None:
        data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "과일 여섯 개일 때 종 쳐도 돼?"}
                        ]
                    }
                }
            ]
        }

        self.assertEqual(_extract_gemini_audio_text(data), "과일 여섯 개일 때 종 쳐도 돼?")

    def test_gemini_direct_answer_request_uses_inline_data_and_json_output(self) -> None:
        client = _make_gms_client("generate-content")

        url, payload = client._gemini_audio_direct_answer_request(
            "룰북으로 답해줘",
            "audio/ogg",
            "YWJj",
        )

        self.assertEqual(url, "https://gms.test/gemini/v1beta/models/gemini-2.5-flash:generateContent")
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
        inline_data = payload["contents"][0]["parts"][1]["inline_data"]
        self.assertEqual(inline_data["data"], "YWJj")
        self.assertEqual(inline_data["mime_type"], "audio/ogg")

    def test_parse_direct_audio_answer_from_json_code_block(self) -> None:
        parsed = _parse_direct_audio_answer(
            '```json\n{"question":"조커는 어떻게 써?", "answer":"조커는 필요한 타일을 대신할 수 있습니다."}\n```'
        )

        self.assertEqual(parsed.question, "조커는 어떻게 써?")
        self.assertEqual(parsed.answer, "조커는 필요한 타일을 대신할 수 있습니다.")

    def test_gemini_transcript_cleanup_removes_prefix(self) -> None:
        self.assertEqual(
            _clean_gemini_transcript('질문: "루미큐브에서 조커는 어떻게 써?"'),
            "루미큐브에서 조커는 어떻게 써?",
        )


def _make_gms_client(style: str, base_url: str = "https://gms.test/gemini") -> GmsClient:
    return GmsClient(
        auth=GmsAuth(api_key="test-key", header="Authorization", scheme="Bearer"),
        endpoints=GmsEndpoints(
            base_url="https://gms.test/openai",
            chat="/v1/chat/completions",
            stt="/v1/audio/transcriptions",
            tts="/v1/audio/speech",
            embeddings="/v1/embeddings",
            models="/v1/models",
            gemini_audio_base_url=base_url,
            gemini_audio_endpoint="/v1beta/interactions" if style == "interactions" else "",
            gemini_audio_request_style=style,
        ),
        models=GmsModels(
            text_model="gpt-4.1-nano",
            stt_model="whisper-1",
            tts_model="gpt-4o-mini-tts",
            embedding_model="text-embedding-3-small",
            tts_voice="alloy",
            tts_response_format="wav",
            temperature=0.2,
            gemini_audio_model="gemini-2.5-flash",
        ),
    )


if __name__ == "__main__":
    unittest.main()
