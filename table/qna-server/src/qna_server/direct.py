from __future__ import annotations

import logging
from contextlib import suppress
from typing import Callable

from .engine import Answer, normalize_answer_tone, normalize_question_for_game
from .gms_client import GmsClient, GmsNoTranscriptError
from .knowledge import RuleKnowledgeBase
from .payloads import QnaStartPayload
from .speech import _record_microphone_wav


class GeminiDirectAnswerer:
    def __init__(
        self,
        knowledge_base: RuleKnowledgeBase,
        client: GmsClient,
        record_seconds: float,
        record_min_seconds: float,
        sample_rate: int,
        channels: int,
        input_device: str,
        silence_seconds: float,
        silence_threshold: int,
        noise_seconds: float,
        threshold_multiplier: float,
    ) -> None:
        self._knowledge_base = knowledge_base
        self._client = client
        self._record_seconds = record_seconds
        self._record_min_seconds = record_min_seconds
        self._sample_rate = sample_rate
        self._channels = channels
        self._input_device = input_device
        self._silence_seconds = silence_seconds
        self._silence_threshold = silence_threshold
        self._noise_seconds = noise_seconds
        self._threshold_multiplier = threshold_multiplier

    def answer(self, start: QnaStartPayload, on_recording_done: Callable[[], None] | None = None) -> Answer:
        chunks = self._knowledge_base.chunks_for_game(start.boardgame_name)
        if not chunks:
            return Answer(
                question="",
                text=(
                    f"{start.boardgame_name} 규칙 문서를 아직 찾지 못했어요. "
                    "게임명을 다시 확인해 주세요."
                ),
            )

        recording = self._record_question_audio()
        if on_recording_done is not None:
            on_recording_done()
        try:
            context = _format_context(chunks)
            result = self._client.answer_rule_question_from_audio(
                audio_path=recording.path,
                boardgame_name=start.boardgame_name,
                context=context,
                players=start.players,
            )
            question = normalize_question_for_game(start.boardgame_name, result.question)
            answer = normalize_answer_tone(result.answer)
            if not question:
                raise GmsNoTranscriptError("Gemini direct answer returned no question text.")
            if not answer:
                raise RuntimeError("Gemini direct answer returned no answer text.")
            return Answer(question=question, text=answer)
        finally:
            with suppress(OSError):
                recording.path.unlink(missing_ok=True)

    def _record_question_audio(self):
        attempts = (
            (
                self._record_seconds,
                self._record_min_seconds,
                self._silence_seconds,
                "normal",
            ),
            (
                max(self._record_seconds, 5.5),
                max(self._record_min_seconds, 2.5),
                max(self._silence_seconds, 1.2),
                "retry",
            ),
        )
        last_error: GmsNoTranscriptError | None = None
        for seconds, min_seconds, silence_seconds, label in attempts:
            recording = _record_microphone_wav(
                seconds,
                min_seconds,
                self._sample_rate,
                self._channels,
                self._input_device,
                silence_seconds,
                self._silence_threshold,
                self._noise_seconds,
                self._threshold_multiplier,
            )
            if recording.heard_speech:
                return recording
            last_error = GmsNoTranscriptError("Microphone recording had no detected speech.")
            with suppress(OSError):
                recording.path.unlink(missing_ok=True)
            if label == "normal":
                logging.info("Microphone recording had no detected speech; retrying with longer recording.")
                continue
            break

        if last_error is not None:
            raise last_error
        raise RuntimeError("Microphone recording failed before Gemini direct answer.")


def _format_context(chunks) -> str:
    return "\n\n".join(
        f"[{chunk.title}]\n{chunk.text}"
        for chunk in chunks
    )
