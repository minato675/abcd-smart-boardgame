"""pipeline.py와 같은 파이프라인(촬영 -> YOLO 탐지 -> 분류 -> 그룹핑 -> 판정)이지만
두 가지가 다르다.

1. 분류(숫자/색상 ResNet) 단계를 타일마다 따로 호출하지 않고, 크롭 전체를 하나의
   배치로 묶어 한 번씩만 호출한다. tesorRT_test/benchmark_full.py 벤치마크에서
   확인한 대로, 이게 TensorRT 전환보다 훨씬 큰 병목 해소 효과가 있었다
   (실측: 타일별 148ms -> 배치 34ms, 약 4.4배).
2. 각 단계(촬영/YOLO 탐지/분류/그룹핑/판정)의 소요 시간을 측정해서 응답에
   "timings_ms" 필드로 함께 담고 콘솔에도 출력한다 -- 실제 보드에서 어느
   단계가 병목인지 바로 관찰하기 위한 용도.

YOLO/그룹핑/판정/카메라 캡처 로직 자체는 pipeline.py 걸 그대로 재사용한다
(중복 구현하지 않음).
"""

import time

import cv2
import numpy as np
import torch
from PIL import Image

import pipeline as p
from pipeline import (
    CAMERA_ENABLED,
    MOCK_IMAGE_DIR,
    _build_display,
    _combine_final_label,
    _crop_with_margin,
    _eval_tf,
    capture_frame,
    group_detections,
    judge_groups,
    load_model,
    unload_model,
)


def analyze_frame_batch(image_bgr: np.ndarray) -> tuple[list[dict], dict[str, float]]:
    """analyze_frame()과 결과 형식은 동일하지만, 숫자/색상 분류를 크롭 전체
    배치로 한 번씩만 호출한다. (detections, {"yolo": 초, "classify": 초}) 반환."""
    if p._yolo_model is None or p._number_model is None or p._color_model is None:
        raise RuntimeError("load_model()을 먼저 호출해야 합니다.")

    t0 = time.perf_counter()
    result = p._yolo_model.predict(
        image_bgr,
        conf=p.YOLO_CONF,
        imgsz=p.YOLO_IMGSZ,
        device="cpu" if p.FORCE_CPU else (0 if torch.cuda.is_available() else "cpu"),
        verbose=False,
    )[0]
    yolo_elapsed = time.perf_counter() - t0

    t0 = time.perf_counter()
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    boxes_xyxy = result.boxes.xyxy.cpu().numpy()
    boxes_conf = result.boxes.conf.cpu().numpy()
    boxes_cls = result.boxes.cls.cpu().numpy().astype(int)

    boxes_kept = []
    crops = []
    for (x1, y1, x2, y2), yolo_conf, yolo_cls_id in zip(boxes_xyxy, boxes_conf, boxes_cls):
        crop = _crop_with_margin(image_rgb, x1, y1, x2, y2)
        if crop is None or crop.size == 0:
            continue
        boxes_kept.append((x1, y1, x2, y2, yolo_conf, yolo_cls_id))
        crops.append(crop)

    detections: list[dict] = []
    if crops:
        batch = torch.stack([_eval_tf(Image.fromarray(c)) for c in crops]).to(p.DEVICE)
        with torch.no_grad():
            number_probs = torch.softmax(p._number_model(batch), dim=1)
            color_probs = torch.softmax(p._color_model(batch), dim=1)
        number_idx = number_probs.argmax(dim=1)
        color_idx = color_probs.argmax(dim=1)

        for i, (x1, y1, x2, y2, yolo_conf, yolo_cls_id) in enumerate(boxes_kept):
            number_pred = p._number_classes[int(number_idx[i])]
            number_conf = float(number_probs[i, number_idx[i]])
            color_pred = p._color_classes[int(color_idx[i])]
            color_conf = float(color_probs[i, color_idx[i]])
            final_label = _combine_final_label(number_pred, color_pred)
            confidence = min(number_conf, color_conf)

            if confidence < p.CONF_THRESHOLD:
                continue  # 임계값 미만인 결과는 버린다

            detections.append(
                {
                    "x1": float(x1), "y1": float(y1), "x2": float(x2), "y2": float(y2),
                    "yolo_class": p._yolo_class_names[yolo_cls_id]
                    if yolo_cls_id < len(p._yolo_class_names) else "?",
                    "yolo_conf": float(yolo_conf),
                    "number_pred": number_pred, "number_conf": number_conf,
                    "color_pred": color_pred, "color_conf": color_conf,
                    "final_label": final_label,
                    "confidence": confidence,
                }
            )
    classify_elapsed = time.perf_counter() - t0  # crop 추출 + 배치 분류 전체 포함

    return detections, {"yolo": yolo_elapsed, "classify": classify_elapsed}


def run_turn(state: dict, turn_id: int) -> dict:
    """pipeline.run_turn()과 같은 진입점이지만, 배치 분류를 쓰고 단계별 소요
    시간을 측정해서 응답의 "timings_ms" 필드(단위 ms)로 함께 반환한다."""
    timings: dict[str, float] = {}
    t_total0 = time.perf_counter()

    t0 = time.perf_counter()
    load_model()
    timings["load_model"] = time.perf_counter() - t0

    try:
        t0 = time.perf_counter()
        frame = capture_frame(turn_id)
        timings["capture"] = time.perf_counter() - t0

        detections, stage_timings = analyze_frame_batch(frame)
        timings["yolo"] = stage_timings["yolo"]
        timings["classify"] = stage_timings["classify"]

        t0 = time.perf_counter()
        groups = group_detections(detections)
        timings["group"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        decision, reason_codes = judge_groups(groups, state)
        timings["judge"] = time.perf_counter() - t0
    finally:
        t0 = time.perf_counter()
        unload_model()
        timings["unload_model"] = time.perf_counter() - t0

    timings["total"] = time.perf_counter() - t_total0
    timings_ms = {k: round(v * 1000, 2) for k, v in timings.items()}

    # FAIL 턴은 상태에 반영하지 않음 (pipeline.run_turn과 동일한 원칙).
    if decision == "PASS":
        state["last_board_labels"] = [label for g in groups for label in g["labels"]]
        state["game_log"].append(
            {
                "turn_id": turn_id,
                "player_id": state["current_player_id"],
                "decision": decision,
                "reason_codes": reason_codes,
            }
        )

    log = {
        "player_id": state["current_player_id"],
        "recheck_count": state.get("recheck_count", 0),
        "groups": groups,
        "image_reference": None,
    }

    response = {
        "request_id": state.get("last_request_id"),
        "game_id": state["game_id"],
        "turn_id": turn_id,
        "decision": decision,
        "reason_codes": reason_codes,
        "display": _build_display(decision, reason_codes),
        "log": log,
        "game_log": state["game_log"],
        "timings_ms": timings_ms,
    }

    print(f"[facilitator2] turn_id={turn_id} player={log['player_id']} decision={decision} "
          f"reason_codes={reason_codes} detections={len(detections)} groups={len(groups)}")
    print("  timings(ms): " + ", ".join(f"{k}={v:.2f}" for k, v in timings_ms.items()))
    for g in groups:
        b = g["bbox"]
        print(f"  group {g['group_id']}: bbox=({b['x1']:.0f},{b['y1']:.0f})-({b['x2']:.0f},{b['y2']:.0f}) "
              f"labels={g['labels']}")

    return response


if __name__ == "__main__":
    if CAMERA_ENABLED:
        print("CAMERA_ENABLED=true 상태입니다 -- image/ 폴더 대신 실제 카메라로 촬영합니다. "
              "폴더 이미지로 테스트하려면 .env에서 CAMERA_ENABLED=false로 바꾸세요.")

    test_state = {
        "game_id": "test-game-2",
        "current_player_id": "player_1",
        "recheck_count": 0,
        "game_log": [],
        "last_request_id": "req-test-2",
        "last_board_labels": [],
        "has_completed_initial_meld": {},
    }

    image_count = len(
        [f for f in MOCK_IMAGE_DIR.iterdir() if f.suffix.lower() in {".jpg", ".jpeg", ".png"}]
    ) if MOCK_IMAGE_DIR.is_dir() else 0
    if image_count == 0 and not CAMERA_ENABLED:
        raise SystemExit(f"테스트할 이미지가 없습니다: {MOCK_IMAGE_DIR.resolve()}")

    turn_count = image_count if not CAMERA_ENABLED else 1
    for turn_id in range(1, turn_count + 1):
        response = run_turn(test_state, turn_id)
