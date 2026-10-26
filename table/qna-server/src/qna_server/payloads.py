from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .topics import parse_qna_start_room


@dataclass(frozen=True)
class QnaStartPayload:
    room_number: str
    transaction_id: str
    boardgame_name: str
    players: int | None = None


@dataclass(frozen=True)
class QnaReadyPayload:
    transactionId: str
    status: str
    msg: str | None = None


@dataclass(frozen=True)
class QnaResultPayload:
    transactionId: str
    req: str
    res: str


def parse_qna_start(topic: str, payload: str | bytes) -> QnaStartPayload:
    room_number = parse_qna_start_room(topic)
    raw_payload = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    data = json.loads(raw_payload or "{}")
    if not isinstance(data, dict):
        raise ValueError("qna/start payload must be a JSON object")

    transaction_id = data.get("transactionId")
    boardgame_name = data.get("boardgameName") or data.get("boardGameName")
    players = data.get("players")

    if not isinstance(transaction_id, str) or not transaction_id.strip():
        raise ValueError("qna/start payload requires transactionId")
    if not isinstance(boardgame_name, str) or not boardgame_name.strip():
        raise ValueError("qna/start payload requires boardgameName or boardGameName")
    if players is not None and not isinstance(players, int):
        raise ValueError("qna/start players must be an integer when present")

    return QnaStartPayload(
        room_number=room_number,
        transaction_id=transaction_id,
        boardgame_name=boardgame_name,
        players=players,
    )


def to_json(payload: object) -> str:
    if hasattr(payload, "__dataclass_fields__"):
        payload = {
            key: value
            for key, value in asdict(payload).items()
            if value is not None
        }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

