"""진행자의 MQTT 입구. Spring(Main Controller)이 /room/{ROOM_NUMBER}/mc/cmd/*로
보내는 명령을 받아 pipeline.py를 호출하고, 결과를 /room/{ROOM_NUMBER}/mc/event/*로
발행한다. FastAPI의 main.py에 해당하는 역할 -- 실제 분석 로직은 pipeline.py 그대로 재사용.
"""

import json
import os

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

import process_lock
import state
from pipeline import run_turn as run_turn_rummikub
from pipeline import warmup_model

load_dotenv()

BROKER_HOST = os.getenv("BROKER_HOST", "localhost")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))
BROKER_USERNAME = os.getenv("BROKER_USERNAME")
BROKER_PASSWORD = os.getenv("BROKER_PASSWORD")
ROOM_NUMBER = os.getenv("ROOM_NUMBER", "1")

# true면 cmd/start를 받았을 때 더미 추론으로 GPU를 미리 데워둔다 (WORKLOG.md 14장의
# 콜드 스타트 현상 대응). 플레이어들이 보드를 세팅하는 시간과 겹쳐서, 첫 cmd/analyze가
# 실제 콜드 스타트 비용을 떠안지 않도록 하기 위함. 기본은 꺼둠(off) -- 게임 시작이
# 그만큼 늦어지므로 필요할 때만 켠다.
WARMUP_ON_START = os.getenv("WARMUP_ON_START", "false").strip().lower() == "true"

TOPIC_PREFIX = f"/room/{ROOM_NUMBER}/mc"
TOPIC_START = f"{TOPIC_PREFIX}/cmd/start"
TOPIC_ANALYZE = f"{TOPIC_PREFIX}/cmd/analyze"
TOPIC_FINISH = f"{TOPIC_PREFIX}/cmd/finish"
TOPIC_TURN_LOG = f"{TOPIC_PREFIX}/event/turn-log"
TOPIC_VIOLATION = f"{TOPIC_PREFIX}/event/violation"
TOPIC_ERROR = f"{TOPIC_PREFIX}/event/error"

# boardgameName -> 그 게임의 run_turn(state, turn_id) 함수. 지금은 럼미큐브 하나뿐이라
# 실질적인 분기는 없지만, 다른 게임이 추가되면 여기 등록만 하면 되는 구조로 만들어뒀다.
# (build_table/VIOLATION_CODE_MAP은 아직 럼미큐브 전용이라, 게임이 늘어나면 그것도
# 게임별로 분리해야 한다 -- 지금은 스코프 밖.)
GAME_HANDLERS = {
    "루미큐브": run_turn_rummikub,
}

# rules.py의 세분화된 reason_code -> 문서에 확정된 event/violation의 code enum
# (DUPLICATE_COLOR, INVALID_SEQUENCE, INSUFFICIENT_TILES, INVALID_INITIAL_MELD,
# COLOR_MISMATCH) 5개로 매핑. TOO_MANY_JOKERS는 문서 enum에 대응하는 항목이 없어서
# 구조적 유효성 문제로 보고 INVALID_SEQUENCE로 매핑했다 -- 팀 확인 필요.
VIOLATION_CODE_MAP = {
    "LESS_THAN_THREE_TILES": "INSUFFICIENT_TILES",
    "MORE_THAN_FOUR_TILES": "INSUFFICIENT_TILES",
    "NUMBER_GAP": "INVALID_SEQUENCE",
    "INVALID_13_TO_1_SEQUENCE": "INVALID_SEQUENCE",
    "DUPLICATE_NUMBER": "INVALID_SEQUENCE",
    "NUMBER_MISMATCH": "INVALID_SEQUENCE",
    "TOO_MANY_JOKERS": "INVALID_SEQUENCE",
    "DUPLICATE_COLOR": "DUPLICATE_COLOR",
    "COLOR_MISMATCH": "COLOR_MISMATCH",
    "INVALID_INITIAL_MELD": "INVALID_INITIAL_MELD",  # 문서 enum과 이름이 같아서 항등 매핑
}

# event/violation의 code(위 VIOLATION_CODE_MAP의 결과값, 문서에 확정된 5개)별로
# 태블릿에 바로 표시할 고정 한국어 문구. reason_code 그대로 노출하지 않고 문서에
# 맞춘 사용자용 메시지로 변환한다.
VIOLATION_MESSAGE_MAP = {
    "DUPLICATE_COLOR": "같은 색상이 중복됩니다.",
    "INVALID_SEQUENCE": "숫자가 올바른 순서로 연결되지 않았습니다.",
    "INSUFFICIENT_TILES": "타일 개수가 올바르지 않습니다.",
    "INVALID_INITIAL_MELD": "초기 멜드 점수(30점)를 채우지 못했습니다.",
    "COLOR_MISMATCH": "같은 색의 연속된 숫자가 아닙니다.",
}


def _parse_label(label: str) -> dict:
    """final_label("red_5", "joker")을 table 항목({"color","number"})으로 변환.
    조커는 number=0, color="black" 고정 (다른 타일과 동일하게 소문자로 통일)."""
    if label == "joker":
        return {"color": "black", "number": 0}
    color, number = label.split("_", 1)
    return {"color": color, "number": int(number)}


def build_table(groups: list[dict]) -> list[list[dict]]:
    """pipeline.group_detections() 결과(groups)를 turn-log payload의 table 형식으로 변환."""
    return [[_parse_label(label) for label in group["labels"]] for group in groups]


def _pick_primary_reason(reason_codes: list[str]) -> str:
    """violation.code는 하나만 보낼 수 있어서, 여러 사유 중 하나를 골라야 한다.
    INVALID_INITIAL_MELD가 있으면 그걸 우선한다 -- "아직 30점을 못 채웠다"가
    "조합이 이상하다"보다 더 근본적인 문제라 플레이어가 먼저 알아야 한다."""
    if "INVALID_INITIAL_MELD" in reason_codes:
        return "INVALID_INITIAL_MELD"
    return reason_codes[0] if reason_codes else "UNKNOWN"


def handle_start(payload: dict) -> None:
    session_id = payload["sessionId"]
    boardgame_name = payload.get("boardgameName", "루미큐브")

    if boardgame_name not in GAME_HANDLERS:
        print(f"[mqtt] 지원하지 않는 게임이라 무시: {boardgame_name} (session={session_id})")
        return

    state.create_session(session_id, boardgame_name)
    print(f"[mqtt] 게임 시작: session={session_id} game={boardgame_name}")

    if WARMUP_ON_START:
        print(f"[mqtt] GPU 워밍업 시작: session={session_id}")
        warmup_model()
        print(f"[mqtt] GPU 워밍업 완료: session={session_id}")


def handle_analyze(payload: dict, client: mqtt.Client) -> None:
    session_id = payload["sessionId"]
    session = state.get_session(session_id)
    if session is None:
        print(f"[mqtt] 알 수 없는 session이라 analyze 무시: {session_id}")
        return

    # playerId는 cmd/analyze마다 실려온다 -- state.py는 더 이상 플레이어를 자체
    # 순환시키지 않고, 매 턴 이 값을 그대로 current_player_id로 씀 (초기 멜드
    # 판정이 플레이어별 상태를 추적해야 해서 필요해짐).
    session["current_player_id"] = payload.get("playerId", "unknown")

    state.advance_turn(session)
    run_turn = GAME_HANDLERS[session["boardgame_name"]]
    result = run_turn(session, session["turn_id"])

    # PASS일 때만 turn-log를 보낸다 -- FAIL(반칙)이면 아직 보드에 확정된 게 아니라서
    # event/violation만 보내고, event/turn-log는 안 보낸다.
    if result["decision"] == "PASS":
        turn_log_payload = {
            "sessionId": session_id,
            "table": build_table(result["log"]["groups"]),
        }
        client.publish(TOPIC_TURN_LOG, json.dumps(turn_log_payload))
        print(f"[mqtt] 발행: {TOPIC_TURN_LOG} {turn_log_payload}")

    if result["decision"] == "FAIL":
        reason_codes = result["reason_codes"]
        internal_code = _pick_primary_reason(reason_codes)
        violation_code = VIOLATION_CODE_MAP.get(internal_code, "INVALID_SEQUENCE")

        # 이번에 고른 사유(internal_code)에 해당하는 그룹들만 table에 담는다 --
        # 같은 사유로 걸린 그룹이 없으면(예: 사유 목록이 비어있는 예외 상황) 안전하게
        # invalid_groups 전체로 폴백한다.
        invalid_groups = result["invalid_groups"]
        target_group_ids = {ig["group_id"] for ig in invalid_groups if ig["reason_code"] == internal_code}
        if not target_group_ids:
            target_group_ids = {ig["group_id"] for ig in invalid_groups}
        violation_groups = [g for g in result["log"]["groups"] if g["group_id"] in target_group_ids]

        violation_payload = {
            "sessionId": session_id,
            "code": violation_code,
            "message": VIOLATION_MESSAGE_MAP.get(violation_code, result["display"]["title"]),
            "table": build_table(violation_groups),
        }
        client.publish(TOPIC_VIOLATION, json.dumps(violation_payload))
        print(f"[mqtt] 발행: {TOPIC_VIOLATION} {violation_payload}")


def handle_finish(payload: dict) -> None:
    session_id = payload["sessionId"]
    reason = payload.get("reason")
    state.end_session(session_id)
    suffix = f" (강제 종료: {reason})" if reason else ""
    print(f"[mqtt] 게임 종료: session={session_id}{suffix}")


def on_connect(client, userdata, flags, rc):
    print(f"[mqtt] 브로커 연결됨 ({BROKER_HOST}:{BROKER_PORT}), rc={rc}")
    client.subscribe(TOPIC_START)
    client.subscribe(TOPIC_ANALYZE)
    client.subscribe(TOPIC_FINISH)
    print(f"[mqtt] 구독 시작: {TOPIC_START}, {TOPIC_ANALYZE}, {TOPIC_FINISH}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        print(f"[mqtt] JSON 파싱 실패: topic={msg.topic} raw={msg.payload!r}")
        return

    print(f"[mqtt] 수신: topic={msg.topic} payload={payload}")

    # 핸들러 하나가 실패해도(카메라 오류, 모델 로드 실패 등) 진행자 프로세스 전체가
    # 죽으면 안 된다 -- 여기서 잡아서 다음 명령을 계속 받을 수 있게 한다.
    try:
        if msg.topic == TOPIC_START:
            handle_start(payload)
        elif msg.topic == TOPIC_ANALYZE:
            handle_analyze(payload, client)
        elif msg.topic == TOPIC_FINISH:
            handle_finish(payload)
    except Exception as exc:
        print(f"[mqtt] 처리 중 오류 발생: topic={msg.topic} error={exc!r}")
        session_id = payload.get("sessionId")
        if session_id is not None:
            error_payload = {
                "sessionId": session_id,
                "errorCode": "MODULE_ERROR",
                "message": str(exc),
            }
            client.publish(TOPIC_ERROR, json.dumps(error_payload))
            print(f"[mqtt] 발행: {TOPIC_ERROR} {error_payload}")


def main() -> None:
    process_lock.acquire_or_exit()  # 같은 폴더에서 이미 실행 중이면 여기서 즉시 종료
    client = mqtt.Client()
    if BROKER_USERNAME:
        client.username_pw_set(BROKER_USERNAME, BROKER_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER_HOST, BROKER_PORT)
    client.loop_forever()


if __name__ == "__main__":
    main()
