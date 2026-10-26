from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Callable, Iterable, Protocol

from .knowledge import RuleChunk, RuleKnowledgeBase


@dataclass(frozen=True)
class Answer:
    question: str
    text: str
    spoken_sentences: int = 0


class RuleAnswerClient(Protocol):
    def answer_rule_question(
        self,
        boardgame_name: str,
        question: str,
        context: str,
        players: int | None,
    ) -> str:
        """Generate an answer from the rulebook context."""


class StreamingRuleAnswerClient(Protocol):
    def stream_rule_answer(
        self,
        boardgame_name: str,
        question: str,
        context: str,
        players: int | None,
    ) -> Iterable[str]:
        """Stream answer deltas from the configured LLM."""


class RuleAnswerEngine:
    """RAG answer engine: retrieve rule chunks, then ask the configured LLM."""

    def __init__(
        self,
        knowledge_base: RuleKnowledgeBase,
        answer_client: RuleAnswerClient | None,
        vector_store=None,
        retrieval_mode: str = "keyword",
    ) -> None:
        self._knowledge_base = knowledge_base
        self._answer_client = answer_client
        self._vector_store = vector_store
        self._retrieval_mode = retrieval_mode.lower()

    def answer(self, boardgame_name: str, question: str, players: int | None = None) -> Answer:
        normalized_question = normalize_question_for_game(boardgame_name, question)
        if not normalized_question:
            raise RuntimeError("STT returned an empty question.")

        fast_answer = _fast_rule_answer(boardgame_name, normalized_question)
        if fast_answer:
            return Answer(question=normalized_question, text=fast_answer)

        chunks = self._search_chunks(boardgame_name, normalized_question, limit=4)

        if not chunks:
            return Answer(
                question=normalized_question,
                text=(
                    f"{boardgame_name} 규칙 문서를 아직 찾지 못했어요. "
                    "게임명과 질문을 다시 확인해 주세요."
                ),
            )

        context = _format_context(chunks)
        if self._answer_client is None:
            return Answer(question=normalized_question, text=_shorten(context))

        text = self._answer_client.answer_rule_question(
            boardgame_name=boardgame_name,
            question=normalized_question,
            context=context,
            players=players,
        )
        text = normalize_answer_tone(text)
        return Answer(question=normalized_question, text=text)

    def answer_streaming(
        self,
        boardgame_name: str,
        question: str,
        players: int | None,
        on_sentence: Callable[[str], None],
    ) -> Answer:
        normalized_question = normalize_question_for_game(boardgame_name, question)
        if not normalized_question:
            raise RuntimeError("STT returned an empty question.")

        fast_answer = _fast_rule_answer(boardgame_name, normalized_question)
        if fast_answer:
            on_sentence(fast_answer)
            return Answer(
                question=normalized_question,
                text=fast_answer,
                spoken_sentences=1,
            )

        chunks = self._search_chunks(boardgame_name, normalized_question, limit=4)
        if not chunks:
            return Answer(
                question=normalized_question,
                text=(
                    f"{boardgame_name} 규칙 문서를 아직 찾지 못했어요. "
                    "게임명과 질문을 다시 확인해 주세요."
                ),
            )
        if self._answer_client is None or not hasattr(self._answer_client, "stream_rule_answer"):
            return self.answer(boardgame_name, normalized_question, players)

        context = _format_context(chunks)
        full_text_parts: list[str] = []
        sentence_buffer = ""
        spoken_sentences = 0

        stream = getattr(self._answer_client, "stream_rule_answer")
        for delta in stream(boardgame_name, normalized_question, context, players):
            if not delta:
                continue
            full_text_parts.append(delta)
            sentence_buffer += delta
            sentences, sentence_buffer = _pop_complete_sentences(sentence_buffer)
            for sentence in sentences:
                sentence = normalize_answer_tone(sentence)
                on_sentence(sentence)
                spoken_sentences += 1

        remaining = sentence_buffer.strip()
        if remaining:
            remaining = normalize_answer_tone(remaining)
            on_sentence(remaining)
            spoken_sentences += 1

        text = normalize_answer_tone("".join(full_text_parts).strip())
        if not text:
            raise RuntimeError("GMS LLM returned no streamed answer.")
        return Answer(
            question=normalized_question,
            text=text,
            spoken_sentences=spoken_sentences,
        )

    def _search_chunks(self, boardgame_name: str, question: str, limit: int) -> list[RuleChunk]:
        keyword_chunks = self._knowledge_base.search(boardgame_name, question, limit=limit)
        if self._vector_store is None or self._retrieval_mode == "keyword":
            return keyword_chunks

        try:
            vector_chunks = self._vector_store.search(boardgame_name, question, limit=limit)
        except Exception:
            logging.exception("VectorDB search failed; falling back to keyword search.")
            return keyword_chunks

        if self._retrieval_mode == "vector":
            return vector_chunks or keyword_chunks

        return _dedupe_chunks([*vector_chunks, *keyword_chunks])[:limit]


def _format_context(chunks) -> str:
    return "\n\n".join(
        f"[{chunk.title}]\n{chunk.text}"
        for chunk in chunks
    )


def _shorten(text: str, max_chars: int = 180) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= max_chars:
        return one_line
    return one_line[: max_chars - 1].rstrip() + "…"


def _dedupe_chunks(chunks: list[RuleChunk]) -> list[RuleChunk]:
    deduped: list[RuleChunk] = []
    seen: set[tuple[str, str, str]] = set()
    for chunk in chunks:
        key = (chunk.game_key, chunk.title, chunk.text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)
    return deduped


QUESTION_REPLACEMENTS = {
    "조카": "조커",
    "초커": "조커",
    "쪼커": "조커",
    "독화": "조커",
}


def normalize_question(question: str) -> str:
    normalized = question.strip()
    for source, target in QUESTION_REPLACEMENTS.items():
        normalized = normalized.replace(source, target)
    return normalized


def normalize_question_for_game(boardgame_name: str, question: str) -> str:
    normalized = normalize_question(question)
    game = boardgame_name.replace(" ", "")
    if "할리갈리" not in game:
        return normalized

    normalized = re.sub(r"동\s*쳐", "종 쳐", normalized)
    normalized = re.sub(r"16\s*개(?=.*종)", "6개", normalized)
    return normalized


def normalize_answer_tone(answer: str) -> str:
    normalized = " ".join(answer.strip().split())
    if not normalized:
        return normalized

    ending = ""
    if normalized[-1] in ".!?。？！":
        ending = normalized[-1]
        normalized = normalized[:-1].rstrip()

    replacements = (
        (r"해야 한다$", "해야 합니다"),
        (r"야 한다$", "야 합니다"),
        (r"해야된다$", "해야 됩니다"),
        (r"해야 된다$", "해야 됩니다"),
        (r"할 수 있다$", "할 수 있습니다"),
        (r"칠 수 있다$", "칠 수 있습니다"),
        (r"쓸 수 있다$", "쓸 수 있습니다"),
        (r"사용할 수 있다$", "사용할 수 있습니다"),
        (r"가능하다$", "가능합니다"),
        (r"불가능하다$", "불가능합니다"),
        (r"된다$", "됩니다"),
        (r"안 된다$", "안 됩니다"),
        (r"없다$", "없습니다"),
        (r"있다$", "있습니다"),
        (r"아니다$", "아닙니다"),
        (r"받는다$", "받습니다"),
        (r"가져간다$", "가져갑니다"),
        (r"넘긴다$", "넘깁니다"),
    )
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized)

    return normalized + (ending or ".")


SENTENCE_PATTERN = re.compile(r"(.+?[.!?。？！])(\s+|$)", re.DOTALL)


KOREAN_COUNTS = {
    "한": 1,
    "하나": 1,
    "두": 2,
    "둘": 2,
    "세": 3,
    "셋": 3,
    "네": 4,
    "넷": 4,
    "다섯": 5,
    "오": 5,
    "여섯": 6,
    "육": 6,
    "일곱": 7,
    "칠": 7,
    "여덟": 8,
    "팔": 8,
    "아홉": 9,
    "구": 9,
    "열": 10,
    "십": 10,
}


def _fast_rule_answer(boardgame_name: str, question: str) -> str | None:
    game = boardgame_name.replace(" ", "")
    compact_question = question.replace(" ", "")

    if "할리갈리" in game and "종" in question:
        count = _extract_count(question)
        if count is not None:
            if count == 5:
                return "네. 같은 과일이 정확히 5개일 때는 종을 칠 수 있습니다."
            return "아니요. 할리갈리는 같은 과일이 정확히 5개일 때만 종을 칠 수 있습니다."
        if "과일" in question or any(word in question for word in ("쳐", "치", "눌", "벨")):
            return "같은 과일이 정확히 5개일 때만 종을 칠 수 있습니다."

    if "루미큐브" in game:
        if "조커" in question:
            return "조커는 필요한 숫자와 색을 대신하며, 회수한 조커는 같은 턴에 바로 사용해야 합니다."
        if "13" in compact_question and "1" in compact_question and any(word in question for word in ("붙", "연속", "뒤")):
            return "13 뒤에는 1을 붙일 수 없습니다."

    return None


def _extract_count(question: str) -> int | None:
    digit_match = re.search(r"(\d+)\s*개", question)
    if digit_match:
        return int(digit_match.group(1))

    for word, value in KOREAN_COUNTS.items():
        if re.search(rf"{re.escape(word)}\s*개", question):
            return value
    return None


def _pop_complete_sentences(buffer: str) -> tuple[list[str], str]:
    sentences: list[str] = []
    consumed = 0

    for match in SENTENCE_PATTERN.finditer(buffer):
        sentences.append(match.group(1).strip())
        consumed = match.end()

    if consumed == 0:
        return [], buffer
    return sentences, buffer[consumed:]
