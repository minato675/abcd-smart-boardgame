"""sessionId별 게임 상태 관리. 인메모리 dict라 프로세스 재시작하면 초기화된다(MVP).

pipeline.run_turn(state, turn_id)이 기대하는 키(game_id, current_player_id,
recheck_count, game_log)를 그대로 갖고 있어서, 여기서 만든 session dict를
run_turn()에 그대로 넘기면 된다.

cmd/start는 인원수(playerCount)를 안 받지만, cmd/analyze에 playerId가 추가되기로
확정되어 current_player_id는 매 analyze 요청마다 mqtt_handler.py가 갱신한다
(state.py 안에서 순환시키던 이전 방식은 더 이상 안 씀).

last_board_labels/has_completed_initial_meld는 초기 멜드(30점) 판정용 -- 직전 턴
보드와 비교(rules.find_new_groups)해서 새로 낸 타일을 찾고, 플레이어별로 이미
통과했는지 추적한다.
"""

_sessions: dict[str, dict] = {}


def create_session(session_id: str, boardgame_name: str) -> dict:
    session = {
        "game_id": session_id,
        "boardgame_name": boardgame_name,
        "turn_id": 0,
        "current_player_id": "unknown",
        "recheck_count": 0,
        "game_log": [],
        "last_board_labels": [],
        "has_completed_initial_meld": {},
    }
    _sessions[session_id] = session
    return session


def get_session(session_id: str) -> dict | None:
    return _sessions.get(session_id)


def advance_turn(session: dict) -> None:
    """analyze 명령이 올 때마다 호출 -- turn_id만 증가시킨다 (플레이어 순환 없음)."""
    session["turn_id"] += 1


def end_session(session_id: str) -> None:
    """게임 종료 -- 세션을 완전히 제거한다. status 플래그만 바꾸고 메모리에 남겨두던
    이전 방식은, 세션이 계속 쌓이기만 하는 문제가 있어서 없앴다. "finish"는 이제
    "이 세션은 끝났고 더 이상 존재하지 않는다"는 확실한 신호다."""
    _sessions.pop(session_id, None)
