from __future__ import annotations

import re
import json
import mimetypes
import base64
import logging
import shutil
import subprocess
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urljoin


class GmsNoTranscriptError(RuntimeError):
    pass


@dataclass(frozen=True)
class GmsModels:
    text_model: str
    stt_model: str
    tts_model: str
    embedding_model: str
    tts_voice: str
    tts_response_format: str
    temperature: float
    gemini_audio_model: str


@dataclass(frozen=True)
class GmsEndpoints:
    base_url: str
    chat: str
    stt: str
    tts: str
    embeddings: str
    models: str
    gemini_audio_base_url: str
    gemini_audio_endpoint: str
    gemini_audio_request_style: str


@dataclass(frozen=True)
class GmsAuth:
    api_key: str
    header: str
    scheme: str


@dataclass(frozen=True)
class DirectAudioAnswer:
    question: str
    answer: str


class GmsClient:
    """
    Client for GMS (Gen AI Management System).

    The default request shapes are OpenAI-compatible because many model gateways expose
    that contract. If the team's GMS uses different paths, configure GMS_*_ENDPOINT
    without changing the QnA pipeline.
    """

    def __init__(self, auth: GmsAuth, endpoints: GmsEndpoints, models: GmsModels) -> None:
        if not auth.api_key:
            raise RuntimeError("GMS API key is required. Set GMS_API_KEY or GENAI_API_KEY.")
        if _looks_like_placeholder_api_key(auth.api_key):
            raise RuntimeError(
                "GMS API key looks invalid. Set GMS_API_KEY to the real ASCII token, "
                "not placeholder text."
            )
        if not endpoints.base_url:
            raise RuntimeError("GMS base URL is required. Set GMS_BASE_URL.")

        self._auth = auth
        self._endpoints = endpoints
        self._models = models

    def transcribe_audio(self, audio_path: Path) -> str:
        import requests

        audio_path = audio_path.resolve()
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        mime_type = mimetypes.guess_type(str(audio_path))[0] or "audio/wav"
        with audio_path.open("rb") as audio_file:
            response = requests.post(
                self._url(self._endpoints.stt),
                headers=self._auth_headers(),
                data={
                    "model": self._models.stt_model,
                    "language": "ko",
                    "response_format": "json",
                },
                files={"file": (audio_path.name, audio_file, mime_type)},
                timeout=90,
            )
        data = self._json(response)
        transcript = _first_string(data, ("text", "transcript", "output_text", "result"))
        if not transcript or _looks_like_stt_prompt_echo(transcript):
            raise GmsNoTranscriptError(f"GMS STT returned no transcript: {data}")
        return transcript.strip()

    def transcribe_audio_with_gemini(self, audio_path: Path) -> str:
        import requests

        audio_path = audio_path.resolve()
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        audio_bytes, mime_type = _prepare_gemini_inline_audio(audio_path)
        audio_base64 = base64.b64encode(audio_bytes).decode("ascii")
        prompt = (
            "이 오디오에서 사용자가 실제로 말한 보드게임 규칙 질문만 한국어로 전사하세요. "
            "설명, 답변, 인사, 따옴표, 접두어는 쓰지 말고 전사 문장만 출력하세요. "
            "잘 들리지 않으면 들리는 단어만 짧게 출력하세요."
        )
        url, payload = self._gemini_audio_transcription_request(prompt, mime_type, audio_base64)

        response = requests.post(
            url,
            headers={**self._gemini_audio_auth_headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=90,
        )
        data = self._json(response)
        transcript = _extract_gemini_audio_text(data)
        if not transcript or _looks_like_stt_prompt_echo(transcript):
            raise GmsNoTranscriptError(f"GMS Gemini audio returned no transcript: {data}")
        transcript = _clean_gemini_transcript(transcript)
        if not transcript:
            raise GmsNoTranscriptError(f"GMS Gemini audio returned empty transcript after cleanup: {data}")
        return transcript

    def answer_rule_question_from_audio(
        self,
        audio_path: Path,
        boardgame_name: str,
        context: str,
        players: int | None,
    ) -> DirectAudioAnswer:
        import requests

        audio_path = audio_path.resolve()
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        audio_bytes, mime_type = _prepare_gemini_inline_audio(audio_path)
        audio_base64 = base64.b64encode(audio_bytes).decode("ascii")
        prompt = _direct_audio_answer_prompt(boardgame_name, context, players)
        url, payload = self._gemini_audio_direct_answer_request(prompt, mime_type, audio_base64)

        response = requests.post(
            url,
            headers={**self._gemini_audio_auth_headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=90,
        )
        data = self._json(response)
        raw_text = _extract_gemini_audio_text(data)
        if not raw_text:
            raise GmsNoTranscriptError(f"GMS Gemini direct answer returned no text: {data}")
        parsed = _parse_direct_audio_answer(raw_text)
        if not parsed.question or not parsed.answer:
            raise GmsNoTranscriptError(f"GMS Gemini direct answer returned invalid JSON: {raw_text}")
        return parsed

    def answer_rule_question(
        self,
        boardgame_name: str,
        question: str,
        context: str,
        players: int | None,
    ) -> str:
        import requests

        response = requests.post(
            self._url(self._endpoints.chat),
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            json={
                "model": self._models.text_model,
                "temperature": self._models.temperature,
                "messages": self._rule_answer_messages(boardgame_name, question, context, players),
            },
            timeout=90,
        )
        data = self._json(response)
        answer = _extract_chat_text(data)
        if not answer:
            raise RuntimeError(f"GMS LLM returned no answer: {data}")
        return answer.strip()

    def stream_rule_answer(
        self,
        boardgame_name: str,
        question: str,
        context: str,
        players: int | None,
    ) -> Iterator[str]:
        import requests

        response = requests.post(
            self._url(self._endpoints.chat),
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            json={
                "model": self._models.text_model,
                "temperature": self._models.temperature,
                "stream": True,
                "messages": self._rule_answer_messages(boardgame_name, question, context, players),
            },
            stream=True,
            timeout=90,
        )
        self._raise_for_status(response)

        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                break
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            delta = _extract_chat_delta(data)
            if delta:
                yield delta

    def synthesize_speech(self, text: str) -> bytes:
        import requests

        response = requests.post(
            self._url(self._endpoints.tts),
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            json={
                "model": self._models.tts_model,
                "voice": self._models.tts_voice,
                "input": text,
                "response_format": self._models.tts_response_format,
            },
            timeout=90,
        )
        self._raise_for_status(response)
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            data = response.json()
            audio = _first_string(data, ("audio", "audio_base64", "data"))
            if not audio:
                raise RuntimeError(f"GMS TTS returned JSON without audio data: {data}")
            import base64

            return base64.b64decode(audio)
        return response.content

    def stream_speech(self, text: str) -> Iterator[bytes]:
        import requests

        response = requests.post(
            self._url(self._endpoints.tts),
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            json={
                "model": self._models.tts_model,
                "voice": self._models.tts_voice,
                "input": text,
                "response_format": self._models.tts_response_format,
            },
            stream=True,
            timeout=90,
        )
        self._raise_for_status(response)
        for chunk in response.iter_content(chunk_size=4096):
            if chunk:
                yield chunk

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        import requests

        if not texts:
            return []

        response = requests.post(
            self._url(self._endpoints.embeddings),
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            json={
                "model": self._models.embedding_model,
                "input": texts,
            },
            timeout=90,
        )
        data = self._json(response)
        embeddings = _extract_embeddings(data)
        if len(embeddings) != len(texts):
            raise RuntimeError(
                f"GMS embeddings returned {len(embeddings)} vectors for {len(texts)} texts."
            )
        return embeddings

    def list_models(self) -> dict[str, Any]:
        import requests

        response = requests.get(
            self._url(self._endpoints.models),
            headers=self._auth_headers(),
            timeout=30,
        )
        return self._json(response)

    def _url(self, endpoint: str) -> str:
        return urljoin(self._endpoints.base_url.rstrip("/") + "/", endpoint.lstrip("/"))

    def _url_from(self, base_url: str, endpoint: str) -> str:
        return urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/"))

    def _auth_headers(self) -> dict[str, str]:
        if not self._auth.scheme:
            return {self._auth.header: self._auth.api_key}
        return {self._auth.header: f"{self._auth.scheme} {self._auth.api_key}"}

    def _gemini_audio_auth_headers(self) -> dict[str, str]:
        base_url = self._endpoints.gemini_audio_base_url or self._endpoints.base_url
        if "generativelanguage.googleapis.com" in base_url:
            return {"x-goog-api-key": self._auth.api_key}
        return self._auth_headers()

    def _gemini_audio_transcription_request(
        self,
        prompt: str,
        mime_type: str,
        audio_base64: str,
    ) -> tuple[str, dict[str, Any]]:
        model = self._models.gemini_audio_model
        base_url = self._endpoints.gemini_audio_base_url or self._endpoints.base_url
        endpoint = self._endpoints.gemini_audio_endpoint
        style = self._endpoints.gemini_audio_request_style.lower()

        if style == "interactions":
            return self._url_from(base_url, endpoint or "/v1beta/interactions"), {
                "model": model,
                "input": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "audio",
                        "data": audio_base64,
                        "mime_type": mime_type,
                    },
                ],
                "temperature": 0,
            }

        if style == "generate-content":
            return self._url_from(base_url, endpoint or f"/v1beta/models/{model}:generateContent"), {
                "system_instruction": {
                    "parts": [
                        {
                            "text": (
                                "오디오를 주의 깊게 듣고 사용자가 실제로 말한 내용만 전사한다. "
                                "확실하지 않은 내용은 추측하지 않는다."
                            )
                        }
                    ]
                },
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": audio_base64,
                                }
                            },
                        ],
                    }
                ],
                "generationConfig": {"temperature": 0},
            }

        if style == "openai-chat":
            return self._url_from(base_url, endpoint or self._endpoints.chat), {
                "model": model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": audio_base64,
                                    "format": _audio_format_from_mime_type(mime_type),
                                },
                            },
                        ],
                    }
                ],
            }

        raise ValueError(f"Unsupported GMS_GEMINI_AUDIO_REQUEST_STYLE: {style}")

    def _gemini_audio_direct_answer_request(
        self,
        prompt: str,
        mime_type: str,
        audio_base64: str,
    ) -> tuple[str, dict[str, Any]]:
        model = self._models.gemini_audio_model
        base_url = self._endpoints.gemini_audio_base_url or self._endpoints.base_url
        endpoint = self._endpoints.gemini_audio_endpoint
        style = self._endpoints.gemini_audio_request_style.lower()
        system_instruction = (
            "너는 보드게임 카페의 한국어 규칙 설명 도우미다. "
            "오디오에서 사용자의 질문을 듣고, 제공된 룰북 발췌만 근거로 답한다. "
            "반드시 JSON 객체 하나만 출력한다."
        )

        if style == "interactions":
            return self._url_from(base_url, endpoint or "/v1beta/interactions"), {
                "model": model,
                "input": [
                    {"type": "text", "text": f"{system_instruction}\n\n{prompt}"},
                    {
                        "type": "audio",
                        "data": audio_base64,
                        "mime_type": mime_type,
                    },
                ],
                "temperature": 0,
            }

        if style == "generate-content":
            return self._url_from(base_url, endpoint or f"/v1beta/models/{model}:generateContent"), {
                "system_instruction": {"parts": [{"text": system_instruction}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": audio_base64,
                                }
                            },
                        ],
                    }
                ],
                "generationConfig": {
                    "temperature": 0,
                    "responseMimeType": "application/json",
                },
            }

        if style == "openai-chat":
            return self._url_from(base_url, endpoint or self._endpoints.chat), {
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"{system_instruction}\n\n{prompt}"},
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": audio_base64,
                                    "format": _audio_format_from_mime_type(mime_type),
                                },
                            },
                        ],
                    }
                ],
            }

        raise ValueError(f"Unsupported GMS_GEMINI_AUDIO_REQUEST_STYLE: {style}")

    def _rule_answer_messages(
        self,
        boardgame_name: str,
        question: str,
        context: str,
        players: int | None,
    ) -> list[dict[str, str]]:
        players_text = f"{players}명" if players is not None else "알 수 없음"
        user_prompt = f"""
보드게임: {boardgame_name}
플레이 인원: {players_text}
사용자 질문: {question}

아래 룰북 발췌만 근거로 한국어로 답변해.
모르면 모른다고 말하고, 룰북에서 확인 가능한 범위만 답해.
답변은 태블릿 화면과 스피커로 바로 나가므로 반드시 1문장으로 짧고 명확하게 말해.
답변은 80자를 넘기지 마.
반드시 친절한 존댓말로 답해. 문장은 "합니다", "됩니다", "없습니다", "있습니다", "해요" 같은 높임말로 끝내.
"해야 한다", "할 수 있다", "된다", "없다" 같은 반말이나 문어체 종결은 절대 쓰지 마.
규칙 질문과 직접 관련 없는 격려, 플레이 조언, 일반적인 설명은 하지 마.
문장 단위 TTS를 위해 각 문장은 반드시 마침표, 물음표, 느낌표 중 하나로 끝내.
번호 목록, 불릿, JSON, Markdown 표는 쓰지 마.

[룰북 발췌]
{context}
""".strip()
        return [
            {
                "role": "system",
                "content": (
                    "너는 보드게임 카페 태블릿의 한국어 규칙 설명 도우미다. "
                    "반드시 제공된 룰북 발췌를 근거로만 답하고, 없는 내용은 추측하지 않는다. "
                    "모든 답변은 사용자가 듣는 안내 음성이므로 자연스러운 존댓말로 말한다."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def _json(response) -> dict[str, Any]:
        GmsClient._raise_for_status(response)
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"GMS returned non-object JSON: {data}")
        return data

    @staticmethod
    def _raise_for_status(response) -> None:
        if response.ok:
            return
        body = response.text.strip()
        if len(body) > 1000:
            body = body[:1000] + "..."
        raise RuntimeError(
            f"GMS request failed: {response.status_code} {response.reason} "
            f"for {response.url}. Response body: {body or '<empty>'}"
        )


def _extract_chat_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
            if isinstance(first.get("text"), str):
                return first["text"]

    return _first_string(data, ("output_text", "text", "answer", "result"))


def _extract_gemini_audio_text(data: dict[str, Any]) -> str:
    openai_text = _extract_chat_text(data)
    if openai_text:
        return openai_text

    output = data.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return " ".join(parts)

    candidates = data.get("candidates")
    if isinstance(candidates, list) and candidates:
        first = candidates[0]
        if isinstance(first, dict):
            content = first.get("content")
            if isinstance(content, dict):
                parts = content.get("parts")
                if isinstance(parts, list):
                    texts = [
                        part.get("text", "")
                        for part in parts
                        if isinstance(part, dict) and isinstance(part.get("text"), str)
                    ]
                    if texts:
                        return " ".join(texts)

    return _first_string(data, ("transcript", "output_text", "text", "result"))


def _direct_audio_answer_prompt(boardgame_name: str, context: str, players: int | None) -> str:
    players_text = f"{players}명" if players is not None else "알 수 없음"
    return f"""
보드게임: {boardgame_name}
플레이 인원: {players_text}

첨부된 오디오는 사용자가 말한 보드게임 규칙 질문입니다.
오디오를 듣고 사용자의 질문을 한국어로 추출한 뒤, 아래 룰북 발췌만 근거로 답변하세요.

반드시 아래 JSON 형식만 출력하세요. Markdown 코드블록이나 설명문은 쓰지 마세요.
{{
  "question": "사용자가 실제로 말한 질문",
  "answer": "룰북 근거 기반의 80자 이하 한국어 존댓말 답변"
}}

답변 규칙:
- 룰북에 없는 내용은 추측하지 마세요.
- 답변은 태블릿 화면과 스피커로 바로 나가므로 1문장으로 짧고 명확하게 말하세요.
- 반드시 "합니다", "됩니다", "없습니다", "있습니다", "해요" 같은 존댓말로 끝내세요.
- "해야 한다", "할 수 있다", "된다", "없다" 같은 반말/문어체 종결은 쓰지 마세요.
- 번호 목록, 불릿, 표는 쓰지 마세요.

[룰북 발췌]
{context}
""".strip()


def _parse_direct_audio_answer(raw_text: str) -> DirectAudioAnswer:
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        text = match.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return DirectAudioAnswer(question="", answer="")
    if not isinstance(data, dict):
        return DirectAudioAnswer(question="", answer="")
    question = data.get("question") or data.get("req") or data.get("transcript")
    answer = data.get("answer") or data.get("res") or data.get("response")
    return DirectAudioAnswer(
        question=question.strip() if isinstance(question, str) else "",
        answer=answer.strip() if isinstance(answer, str) else "",
    )


def _clean_gemini_transcript(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"^```(?:text)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    cleaned = re.sub(r"^(전사|질문|사용자 질문|Transcript)\s*[:：]\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip().strip('"').strip("'").strip()


def _audio_format_from_mime_type(mime_type: str) -> str:
    if "mpeg" in mime_type or "mp3" in mime_type:
        return "mp3"
    if "flac" in mime_type:
        return "flac"
    if "ogg" in mime_type:
        return "ogg"
    return "wav"


def _prepare_gemini_inline_audio(audio_path: Path) -> tuple[bytes, str]:
    source_bytes = audio_path.read_bytes()
    source_mime_type = mimetypes.guess_type(str(audio_path))[0] or "audio/wav"
    if source_mime_type in {"audio/ogg", "audio/flac", "audio/mpeg", "audio/mp3"}:
        logging.info(
            "Gemini audio prepared without conversion: mime=%s bytes=%s",
            source_mime_type,
            len(source_bytes),
        )
        return source_bytes, source_mime_type

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg is required for Gemini audio mode. "
            "Install it on Jetson with `sudo apt-get install -y ffmpeg`."
        )

    output_name = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="qna-gemini-audio-", suffix=".ogg", delete=False) as output:
            output_name = output.name
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(audio_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "libvorbis",
                "-b:a",
                "32k",
                "-f",
                "ogg",
                output_name,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        output_bytes = Path(output_name).read_bytes()
        logging.info(
            "Gemini audio compressed: sourceMime=%s sourceBytes=%s targetMime=audio/ogg targetBytes=%s",
            source_mime_type,
            len(source_bytes),
            len(output_bytes),
        )
        return output_bytes, "audio/ogg"
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"ffmpeg failed to compress Gemini audio: {detail or exc}") from exc
    finally:
        if output_name:
            with suppress(OSError):
                Path(output_name).unlink(missing_ok=True)


def _extract_chat_delta(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            delta = first.get("delta")
            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                return delta["content"]
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
            if isinstance(first.get("text"), str):
                return first["text"]

    return _first_string(data, ("delta", "output_text", "text"))


def _first_string(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            return value
    return ""


def _extract_embeddings(data: dict[str, Any]) -> list[list[float]]:
    raw_items = data.get("data")
    if isinstance(raw_items, list):
        ordered_items = sorted(
            (item for item in raw_items if isinstance(item, dict)),
            key=lambda item: item.get("index", 0),
        )
        embeddings = [_coerce_embedding(item.get("embedding")) for item in ordered_items]
        return [embedding for embedding in embeddings if embedding]

    raw_embeddings = data.get("embeddings")
    if isinstance(raw_embeddings, list):
        return [
            embedding
            for embedding in (_coerce_embedding(item) for item in raw_embeddings)
            if embedding
        ]

    return []


def _coerce_embedding(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    embedding: list[float] = []
    for item in value:
        if isinstance(item, (int, float)):
            embedding.append(float(item))
        else:
            return []
    return embedding


def _looks_like_placeholder_api_key(value: str) -> bool:
    stripped = value.strip()
    if stripped != value:
        return True
    lowered = stripped.lower()
    placeholders = {
        "네 gms api key",
        "your gms api key",
        "your_gms_api_key",
        "gms api key",
        "api key",
    }
    if lowered in placeholders:
        return True
    return any(ord(character) > 127 for character in stripped)


def _looks_like_stt_prompt_echo(value: str) -> bool:
    compact = re.sub(r"\s+", "", value)
    return any(
        phrase in compact
        for phrase in (
            "사용자가말한질문만",
            "한국어로전사하세요",
            "보드게임규칙질문입니다",
        )
    )


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", value).strip("-")
    return cleaned or "qna-answer"
