"""Jetson에서 카메라로 사진을 찍어 파이프라인 결과를 바로 확인하는 1회성 스크립트.

촬영/YOLO/분류/그룹핑/판정 단계별 소요 시간을 측정해서 콘솔과 결과 JSON에 남긴다.

.env에서 CAMERA_ENABLED=true여야 실제 카메라로 촬영한다 (false면 MOCK_IMAGE_DIR에서 읽음).
"""

import json
import time
from datetime import datetime
from pathlib import Path

import cv2

from pipeline import (
    _build_display,
    analyze_frame,
    capture_frame,
    group_detections,
    judge_groups,
    load_model,
    unload_model,
)
from rules import validate_group

RESULT_DIR = Path("jt_result")
RESULT_DIR.mkdir(parents=True, exist_ok=True)

# 그룹마다 다른 색으로 그려서 구분한다 (그룹 수가 많아지면 색을 순환).
GROUP_COLORS = [
    (0, 255, 0), (255, 0, 0), (0, 0, 255), (0, 255, 255),
    (255, 0, 255), (255, 255, 0), (128, 0, 255), (0, 128, 255),
]

OK_COLOR = (0, 180, 0)
FAIL_COLOR = (0, 0, 255)


def _check_groups(groups: list[dict]) -> list[dict]:
    """그룹별로 rules.validate_group()을 돌려서 valid 여부/reason_code를 붙인다."""
    checked = []
    for group in groups:
        result = validate_group(group["labels"])
        checked.append(
            {
                "group_id": group["group_id"],
                "labels": group["labels"],
                "valid": result.valid,
                "reason_code": None if result.valid else result.reason_code,
                "reason": result.reason,
            }
        )
    return checked


def annotate_frame(image_bgr, groups: list[dict], group_checks: list[dict]):
    """그룹 bbox(굵은 테두리)와 타일별 bbox+라벨(얇은 테두리)을 그리고, 그룹마다
    rule 검사 결과(OK 또는 실패 사유)를 초록/빨강 텍스트로 함께 표시한다."""
    annotated = image_bgr.copy()
    checks_by_id = {c["group_id"]: c for c in group_checks}
    for group in groups:
        color = GROUP_COLORS[group["group_id"] % len(GROUP_COLORS)]
        gb = group["bbox"]
        cv2.rectangle(
            annotated, (int(gb["x1"]), int(gb["y1"])), (int(gb["x2"]), int(gb["y2"])), color, 3
        )
        cv2.putText(
            annotated, f"group {group['group_id']}",
            (int(gb["x1"]), max(0, int(gb["y1"]) - 10)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA,
        )

        check = checks_by_id.get(group["group_id"])
        if check is not None:
            check_text = "OK" if check["valid"] else f"FAIL: {check['reason_code']}"
            check_color = OK_COLOR if check["valid"] else FAIL_COLOR
            cv2.putText(
                annotated, check_text,
                (int(gb["x1"]), int(gb["y2"]) + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, check_color, 2, cv2.LINE_AA,
            )

        for tile in group["tiles"]:
            tb = tile["bbox"]
            cv2.rectangle(
                annotated, (int(tb["x1"]), int(tb["y1"])), (int(tb["x2"]), int(tb["y2"])), color, 1
            )
            cv2.putText(
                annotated, tile["label"],
                (int(tb["x1"]), max(0, int(tb["y1"]) - 4)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2, cv2.LINE_AA,
            )
    return annotated


def run_once(state: dict) -> dict:
    """촬영 -> 분석 -> 그룹핑 -> 판정을 한 번 실행하고, 결과 이미지/JSON을 저장한 뒤
    응답 dict(timings_ms 포함)를 반환한다. mqtt_handler.py의 run_turn()과 동일하게
    load_model()/unload_model()을 호출한다."""
    timings: dict[str, float] = {}
    t_total0 = time.perf_counter()

    t0 = time.perf_counter()
    load_model()
    timings["load_model"] = time.perf_counter() - t0

    try:
        t0 = time.perf_counter()
        frame = capture_frame(0)
        timings["capture"] = time.perf_counter() - t0

        detections, stage_timings = analyze_frame(frame)
        timings.update(stage_timings)

        t0 = time.perf_counter()
        groups = group_detections(detections)
        timings["group"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        decision, reason_codes, invalid_groups = judge_groups(groups, state)
        timings["judge"] = time.perf_counter() - t0

        # pipeline.run_turn()과 동일한 원칙: PASS일 때만 상태에 반영.
        if decision == "PASS":
            state["last_board_labels"] = [label for g in groups for label in g["labels"]]
    finally:
        t0 = time.perf_counter()
        unload_model()
        timings["unload_model"] = time.perf_counter() - t0

    timings["total"] = time.perf_counter() - t_total0
    timings_ms = {k: round(v * 1000, 2) for k, v in timings.items()}

    group_checks = _check_groups(groups)
    display = _build_display(decision, reason_codes, invalid_groups)

    annotated = annotate_frame(frame, groups, group_checks)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_path = RESULT_DIR / f"capture_{timestamp}.jpg"
    cv2.imwrite(str(image_path), annotated)

    result = {
        "decision": decision,
        "reason_codes": reason_codes,
        "display": display,
        "groups": group_checks,
        "image_reference": image_path.name,
        "timings_ms": timings_ms,
    }
    json_path = RESULT_DIR / f"capture_{timestamp}.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"decision={decision} reason_codes={reason_codes}")
    print("timings(ms): " + ", ".join(f"{k}={v:.2f}" for k, v in timings_ms.items()))
    for check in group_checks:
        status = "OK" if check["valid"] else f"FAIL({check['reason_code']})"
        print(f"  group {check['group_id']}: {status} labels={check['labels']}")
    print(f"결과 이미지: {image_path.name}, JSON: {json_path.name}")

    return result


if __name__ == "__main__":
    state = {
        "game_id": "jt-oneshot",
        "current_player_id": "player_1",
        "recheck_count": 0,
        "game_log": [],
        "last_board_labels": [],
        "has_completed_initial_meld": {},
        "last_request_id": "req-jt-oneshot",
    }

    run_once(state)
