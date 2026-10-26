from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
KOREAN_PARTICLES = (
    "으로부터",
    "에게서",
    "한테서",
    "으로써",
    "으로서",
    "까지",
    "부터",
    "에서",
    "에게",
    "한테",
    "보다",
    "처럼",
    "만큼",
    "으로",
    "라고",
    "하고",
    "이며",
    "이고",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "도",
    "만",
    "과",
    "와",
    "로",
)

TOKEN_ALIASES = {
    "루미큐": "루미큐브",
    "루미큐브": "루미큐브",
    "rummikub": "루미큐브",
    "joker": "조커",
    "조카": "조커",
    "초커": "조커",
    "쪼커": "조커",
}

GAME_ALIASES = {
    "루미큐브": "rummikub",
    "rummikub": "rummikub",
    "할리갈리": "halligalli",
    "halligalli": "halligalli",
    "딕싯": "dixit",
    "dixit": "dixit",
    "스텔라": "stella",
    "stella": "stella",
}


@dataclass(frozen=True)
class RuleChunk:
    game_key: str
    title: str
    text: str


class RuleKnowledgeBase:
    def __init__(self, chunks: list[RuleChunk]) -> None:
        self._chunks = chunks

    @property
    def chunks(self) -> list[RuleChunk]:
        return list(self._chunks)

    @classmethod
    def load(cls, rule_dir: Path) -> "RuleKnowledgeBase":
        chunks: list[RuleChunk] = []
        if not rule_dir.exists():
            return cls(chunks)

        for path in sorted(rule_dir.glob("*.md")):
            game_key = _normalize_game_key(path.stem)
            chunks.extend(_parse_markdown_chunks(path, game_key))

        return cls(chunks)

    def search(self, boardgame_name: str, question: str, limit: int = 3) -> list[RuleChunk]:
        target_chunks = self.chunks_for_game(boardgame_name)
        if not target_chunks:
            return []

        question_tokens = set(_tokens(question))
        scored: list[tuple[int, RuleChunk]] = []

        for chunk in target_chunks:
            score = 0
            chunk_text = f"{chunk.title} {chunk.text}"
            title_tokens = set(_tokens(chunk.title))
            chunk_tokens = set(_tokens(chunk_text))
            score += len(question_tokens & chunk_tokens) * 3
            score += len(question_tokens & title_tokens) * 8
            normalized_chunk_text = _normalize_match_text(chunk_text)
            normalized_title_text = _normalize_match_text(chunk.title)
            for token in question_tokens:
                if len(token) >= 2 and token == normalized_title_text:
                    score += 10
                if len(token) >= 2 and token in normalized_chunk_text:
                    score += 2
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        if scored:
            return [chunk for _, chunk in scored[:limit]]
        return target_chunks[:limit]

    def chunks_for_game(self, boardgame_name: str) -> list[RuleChunk]:
        game_keys = game_keys_for(boardgame_name)
        target_chunks = [chunk for chunk in self._chunks if chunk.game_key in game_keys]
        if target_chunks:
            return target_chunks
        return [chunk for chunk in self._chunks if chunk.game_key == "default"]


def game_keys_for(value: str) -> set[str]:
    return _game_keys(value)


def _parse_markdown_chunks(path: Path, game_key: str) -> list[RuleChunk]:
    chunks: list[RuleChunk] = []
    current_title = path.stem
    current_lines: list[str] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            _append_chunk(chunks, game_key, current_title, current_lines)
            current_title = line.lstrip("#").strip() or path.stem
            current_lines = []
            continue
        current_lines.append(line)

    _append_chunk(chunks, game_key, current_title, current_lines)
    return chunks


def _append_chunk(
    chunks: list[RuleChunk],
    game_key: str,
    title: str,
    lines: list[str],
) -> None:
    text = "\n".join(lines).strip()
    if text:
        chunks.append(RuleChunk(game_key=game_key, title=title, text=text))


def _normalize_game_key(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).lower()


def _game_keys(value: str) -> set[str]:
    normalized = _normalize_game_key(value)
    return {normalized, GAME_ALIASES.get(normalized, normalized)}


def _tokens(value: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()

    for token in TOKEN_PATTERN.findall(value):
        normalized = token.lower()
        candidates = {normalized, _strip_particle(normalized)}
        for candidate in list(candidates):
            alias = TOKEN_ALIASES.get(candidate)
            if alias:
                candidates.add(alias)

        for candidate in candidates:
            if candidate and candidate not in seen:
                tokens.append(candidate)
                seen.add(candidate)

    return tokens


def _strip_particle(token: str) -> str:
    for particle in KOREAN_PARTICLES:
        if token.endswith(particle) and len(token) > len(particle) + 1:
            return token[: -len(particle)]
    return token


def _normalize_match_text(value: str) -> str:
    return " ".join(_tokens(value))
