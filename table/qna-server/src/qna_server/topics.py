from __future__ import annotations

import re


QNA_START_PATTERN = re.compile(r"^/room/([^/]+)/qna/start$")


def parse_qna_start_room(topic: str) -> str:
    match = QNA_START_PATTERN.match(topic)
    if not match:
        raise ValueError(f"Unsupported qna/start topic: {topic}")
    return match.group(1)


def qna_ready_topic(room_number: str) -> str:
    return f"/room/{room_number}/qna/ready"


def qna_result_topic(room_number: str) -> str:
    return f"/room/{room_number}/qna/res"


def qna_thinking_topic(room_number: str) -> str:
    return f"/room/{room_number}/qna/thinking"


def wake_start_listen_topic(room_number: str) -> str:
    return f"/room/{room_number}/wake/start-listen"

