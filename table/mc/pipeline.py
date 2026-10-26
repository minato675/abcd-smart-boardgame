"""촬영 -> YOLO(tile 위치 탐지) -> 분류(숫자/색상) -> 최종 라벨까지 한 번에 처리.
infer_test_images_8v.ipynb의 파이프라인(YOLOv8s 1클래스 tile 디텍터 + ResNet18 x2)을
파일 경로 입력 대신 카메라 캡처 입력으로 바꾼 것.
"""

import glob
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from dotenv import load_dotenv
from PIL import Image
from torchvision import models, transforms
from ultralytics import YOLO

from rules import find_new_groups, order_run_labels, validate_group, validate_initial_meld

load_dotenv()  # facilitator/.env 로드 -- CAMERA_ENABLED 등

WEIGHTS_DIR = Path("weights")

YOLO_CONF = 0.6
YOLO_IMGSZ = 960
MARGIN_RATIO = 0.10
IMG_SIZE = 96
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# CAMERA_ENABLED=false면 실제 카메라 대신 MOCK_IMAGE_DIR 폴더의 이미지를 순서대로 읽어온다
# (카메라 없이 목업 테스트용). turn_id 기준으로 폴더 안 이미지를 순환시킨다.
CAMERA_ENABLED = os.getenv("CAMERA_ENABLED", "true").strip().lower() == "true"
CAMERA_DEVICE_INDEX = int(os.getenv("CAMERA_DEVICE_INDEX", "0"))
MOCK_IMAGE_DIR = Path(os.getenv("MOCK_IMAGE_DIR", "image"))

# 열자마자 찍은 첫 프레임은 노출/화이트밸런스 자동조정이 덜 끝나 어둡게 나오는 경우가
# 많아서, 이 프레임 수만큼 읽어 버리고 마지막 프레임만 실제로 쓴다.
CAMERA_WARMUP_FRAMES = int(os.getenv("CAMERA_WARMUP_FRAMES", "15"))

# 평균 밝기가 이 값 미만이면 "열기/읽기는 성공했지만 화면은 까맣다"로 간주하고
# 수동 노출 재시도로 넘어간다 (check_cameras.py에서 검증된 값과 동일).
CAMERA_DARK_FRAME_THRESHOLD = float(os.getenv("CAMERA_DARK_FRAME_THRESHOLD", "10.0"))

# auto-exposure로도 밝아지지 않을 때 수동으로 시도해볼 노출 값들 (V4L2/UVC 기준).
CAMERA_MANUAL_EXPOSURE_TRIES = [-4, -2, 100, 300, 600]

# 숫자/색상 분류기 confidence(둘 중 낮은 쪽)가 이 값 미만이면 결과에서 아예 제외한다.
CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", "0.85"))

# true면 초기 멜드(등록, 30점) 검사를 건너뛰고 모든 플레이어를 이미 등록된 것으로
# 취급한다. 시연 때 "등록"부터 다시 보여줄 필요 없이 바로 진행하고 싶을 때 켠다.
# 실제 규칙 검증(judge_groups)의 다른 부분(런/세트 유효성)은 그대로 동작한다.
DEMO_SKIP_INITIAL_MELD = os.getenv("DEMO_SKIP_INITIAL_MELD", "false").strip().lower() == "true"

# 타일 그룹핑(멜드 분리) 1단계: MST 기반 지역 적응형 클러스터링(_cluster_by_mst)에서
# 쓰는 기준. 전역/행 단위 고정 임계값 대신, 어떤 간선이 자신과 맞닿은 다른 간선들의
# 평균 길이보다 INCONSISTENT_EDGE_RATIO배 이상 길면 서로 다른 멜드 사이의 경계로 보고
# 끊는다 (Zahn's inconsistent edge). MIN_SPLIT_GAP_RATIO는 주변 간선이 전부 0에 가까운
# 밀집 구간에서도 최소한 평균 타일 크기의 이 비율만큼은 벌어져야 경계로 인정하는 하한선.
INCONSISTENT_EDGE_RATIO = 2.5
MIN_SPLIT_GAP_RATIO = 0.2

# 2단계 라벨 기반 재분할(_semantic_resplit)에서 쓰는 기준.
# MAX_MELD_SIZE: 런은 최대 13장(1~13)까지 가능하므로 그 이상은 후보로 보지 않는다.
# SEMANTIC_SPLIT_MAX_TILES: 이보다 큰 무효 그룹은 재분할을 시도하지 않는다 -- 기하
# 정보 자체가 심하게 뒤섞였다는 뜻이라(대각선 중첩 등), DP를 돌려도 못 찾을 가능성이
# 높고 불필요한 연산만 늘어난다.
# ROW_OVERLAP_RATIO: 두 bbox의 y축 겹침이 더 작은 쪽 높이의 이 비율 이상이면
# 같은 행으로 본다 -- x축 순서 DP를 시도하기 전에 서로 다른 행이 섞인 경우를 먼저 걸러낸다.
MAX_MELD_SIZE = 13
SEMANTIC_SPLIT_MAX_TILES = 20
ROW_OVERLAP_RATIO = 0.5

# true면 GPU가 있어도 강제로 CPU만 쓴다 -- Jetson의 CMA(GPU 전용 메모리 풀)를 다른
# 서비스(wake word, 팀원 서버 등)와 공유하다 생기는 경합을 완전히 피하고 싶을 때 켠다.
# 대신 YOLO/분류기 추론이 훨씬 느려진다(실시간성 요구사항과 상충 -- ARCHITECTURE.md SS20.3).
FORCE_CPU = os.getenv("FORCE_CPU", "false").strip().lower() == "true"

# true(기본값)면 unload_model()이 실제로 GPU 메모리를 비워서 유휴 시 CMA 점유를 0으로
# 만든다 (팀원 서비스와 GPU 공유 목적). false면 unload_model()이 아무것도 안 하고
# 모델을 계속 로드된 채로 둔다 -- load_model()은 이미 로드돼 있으면 바로 반환하므로,
# 이 토글 하나만 끄면 자연스럽게 "게임 진행 중엔 계속 로드 유지" 모드가 된다.
# WORKLOG.md 14장에서 확인한 대로 매 턴 로드/해제 자체가 콜드 스타트를 다시 유발할 수
# 있어서, CMA 여유가 있는 상황(팀원 서비스와 안 겹치는 시연 등)이라면 꺼두는 게 더 빠르다.
RELEASE_GPU_ON_IDLE = os.getenv("RELEASE_GPU_ON_IDLE", "true").strip().lower() == "true"

DEVICE = torch.device("cpu") if FORCE_CPU else torch.device("cuda" if torch.cuda.is_available() else "cpu")

_eval_tf = transforms.Compose(
    [
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ]
)

# run_turn()이 요청마다 load_model() -> 추론 -> unload_model()로 채웠다 비운다.
# Jetson을 팀원 서비스와 같이 쓰는데 그쪽은 상시 GPU를 점유하는 구조라, 평소에는 이쪽이
# GPU/CMA를 아예 안 잡고 있다가 요청이 왔을 때만 짧게 점유하는 쪽으로 맞췄다
# (ARCHITECTURE.md SS20.12의 "1회만 로드" 방침과는 다른 선택 -- 반복 로드 비용을
# 감수하고 유휴 시 GPU 점유를 0으로 만드는 쪽을 택함).
_yolo_model: YOLO | None = None
_yolo_class_names: list[str] = []
_number_model: nn.Module | None = None
_number_classes: list[str] = []
_color_model: nn.Module | None = None
_color_classes: list[str] = []


def _build_resnet_classifier(num_classes: int) -> nn.Module:
    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    return model.to(DEVICE)


def _load_classifier(weights_path: Path) -> tuple[nn.Module, list[str]]:
    ckpt = torch.load(weights_path, map_location=DEVICE)
    classes = ckpt["classes"]
    model = _build_resnet_classifier(len(classes))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model, classes


def load_model() -> None:
    """run_turn() 시작 시 매번 호출 -- 이미 로드돼 있으면 아무것도 안 함(중복 로드 방지)."""
    global _yolo_model, _yolo_class_names, _number_model, _number_classes, _color_model, _color_classes

    if _yolo_model is not None:
        return

    _yolo_model = YOLO(str(WEIGHTS_DIR / "yolov8s_tile_detector_best.pt"))
    _yolo_class_names = [_yolo_model.names[i] for i in sorted(_yolo_model.names)]
    _number_model, _number_classes = _load_classifier(WEIGHTS_DIR / "resnet18_number_best.pt")
    _color_model, _color_classes = _load_classifier(WEIGHTS_DIR / "resnet18_color_best.pt")


def unload_model() -> None:
    """run_turn() 끝날 때마다 호출 -- GPU 메모리를 비워서 유휴 시 CMA 점유를 0으로 만든다.
    RELEASE_GPU_ON_IDLE=false면 아무것도 안 하고 모델을 계속 로드된 채로 둔다."""
    if not RELEASE_GPU_ON_IDLE:
        return

    global _yolo_model, _yolo_class_names, _number_model, _number_classes, _color_model, _color_classes

    _yolo_model = None
    _yolo_class_names = []
    _number_model = None
    _number_classes = []
    _color_model = None
    _color_classes = []

    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def warmup_model() -> None:
    """더미 입력으로 YOLO/분류기를 한 번 미리 추론시켜서 GPU 콜드 스타트 비용을
    실제 요청이 오기 전에 치른다 (WORKLOG.md 14장: Jetson GPU가 유휴 상태에서
    막 깨어날 때 첫 추론이 몇 배씩 느려지는 현상 대응). YOLO 탐지는 더미 이미지에서
    아무것도 안 잡힐 수 있어서, 분류기 쪽은 탐지 결과와 무관하게 더미 텐서로
    따로 한 번 더 돌려준다. load_model()/unload_model()을 자체적으로 호출하므로
    호출 전후 모델 로드 상태를 신경 쓸 필요 없다."""
    load_model()
    try:
        dummy_frame = np.zeros((YOLO_IMGSZ, YOLO_IMGSZ, 3), dtype=np.uint8)
        _yolo_model.predict(
            dummy_frame,
            conf=YOLO_CONF,
            imgsz=YOLO_IMGSZ,
            device="cpu" if FORCE_CPU else (0 if torch.cuda.is_available() else "cpu"),
            verbose=False,
        )

        dummy_crop = np.zeros((IMG_SIZE, IMG_SIZE, 3), dtype=np.uint8)
        dummy_tensor = _eval_tf(Image.fromarray(dummy_crop)).unsqueeze(0).to(DEVICE)
        with torch.no_grad():
            _number_model(dummy_tensor)
            _color_model(dummy_tensor)
    finally:
        unload_model()


def capture_frame(turn_id: int = 0) -> np.ndarray:
    """CAMERA_ENABLED=true면 실제 카메라, false면 MOCK_IMAGE_DIR의 이미지를 순서대로 반환."""
    if CAMERA_ENABLED:
        return _capture_from_camera_auto()
    return _capture_from_mock_dir(turn_id)


# _capture_from_camera_auto()가 한 번 찾은 인덱스를 캐싱해두는 곳. 매 턴마다 전체
# 인덱스를 다시 스캔하면 느려지므로, 성공한 인덱스는 재사용하고 실패할 때만 재탐색한다.
_detected_camera_index: int | None = None


def _candidate_camera_indices() -> list[int]:
    """실제 연결된 카메라 장치 인덱스 후보를 시스템에서 찾는다. Linux(Jetson)는
    /dev/video*를 스캔해서 존재하는 인덱스만 후보로 삼고(카메라 하나가 캡처용/
    메타데이터용으로 노드를 여러 개 쓰는 경우가 많아 실패하는 인덱스도 섞여 있을 수
    있음 -- 그래서 _capture_from_camera()의 밝기 체크로 결국 걸러진다), Windows는
    /dev/video* 같은 목록이 없어서 작은 범위를 순차로 시도한다."""
    if sys.platform == "win32":
        return list(range(5))
    indices = []
    for path in sorted(glob.glob("/dev/video*")):
        try:
            indices.append(int(path.replace("/dev/video", "")))
        except ValueError:
            continue
    return sorted(indices)


def _capture_from_camera_auto() -> np.ndarray:
    """CAMERA_DEVICE_INDEX를 먼저 시도하고, 실패하면 시스템에 연결된 다른 카메라
    인덱스를 순서대로 자동 탐색해서 실제로 프레임을 주는 첫 번째 장치를 찾는다.
    찾은 인덱스는 _detected_camera_index에 캐싱해서 다음 호출부터는 바로 그
    인덱스로 시도하고, 캐싱된 인덱스가 나중에 실패하면(장치가 빠졌다 다른 노드로
    다시 잡히는 등) 캐시를 버리고 재탐색한다."""
    global _detected_camera_index

    if _detected_camera_index is not None:
        try:
            return _capture_from_camera(_detected_camera_index)
        except RuntimeError:
            print(f"[camera] 캐싱된 index={_detected_camera_index}가 더 이상 동작하지 않아 재탐색합니다.")
            _detected_camera_index = None

    candidates = [CAMERA_DEVICE_INDEX] + [
        i for i in _candidate_camera_indices() if i != CAMERA_DEVICE_INDEX
    ]
    last_error: Exception | None = None
    for index in candidates:
        try:
            frame = _capture_from_camera(index)
        except RuntimeError as exc:
            last_error = exc
            continue
        if index != CAMERA_DEVICE_INDEX:
            print(f"[camera] CAMERA_DEVICE_INDEX={CAMERA_DEVICE_INDEX}는 실패, "
                  f"대신 index={index}에서 카메라를 찾았습니다.")
        _detected_camera_index = index
        return frame

    raise RuntimeError(
        f"연결된 카메라 중 사용 가능한 장치를 찾지 못했습니다 (시도한 인덱스: {candidates})."
    ) from last_error


def _mean_brightness(frame: np.ndarray) -> float:
    return float(np.mean(frame))


def _read_warmed_up_frame(cap: cv2.VideoCapture) -> np.ndarray | None:
    """워밍업 프레임을 버리고 마지막 프레임만 반환 (읽기 실패 시 None)."""
    frame = None
    for _ in range(CAMERA_WARMUP_FRAMES):
        ok, frame = cap.read()
        if not ok:
            return None
    return frame


def _try_manual_exposure(cap: cv2.VideoCapture) -> tuple[np.ndarray | None, float]:
    """auto-exposure를 끄고 여러 노출 값으로 재시도해서 가장 밝은 프레임을 찾는다.
    check_cameras.py로 진단했을 때, Jetson UVC 드라이버가 auto-exposure 수렴에
    실패해 프레임이 계속 새까맣게 나오는 경우가 확인돼서 실제 촬영 경로에도 반영한다."""
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # V4L2 관례: 0.25=manual, 0.75=auto

    best_frame, best_brightness = None, 0.0
    for exposure in CAMERA_MANUAL_EXPOSURE_TRIES:
        cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
        frame = _read_warmed_up_frame(cap)
        if frame is None:
            continue
        brightness = _mean_brightness(frame)
        if brightness > best_brightness:
            best_frame, best_brightness = frame, brightness
        if best_brightness >= CAMERA_DARK_FRAME_THRESHOLD:
            break

    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)  # 다음 촬영을 위해 auto로 복원
    return best_frame, best_brightness


def _capture_from_camera(device_index: int) -> np.ndarray:
    """Windows는 카메라마다 DSHOW/MSMF 중 한쪽으로만 잡히는 경우가 있어서(구형
    DirectShow 필터만 있는 카메라 vs 최신 Media Foundation 전용 카메라), 기본
    백엔드(MSMF)를 먼저 시도하고 실패하면 DSHOW로 한 번 더 시도한다.
    Jetson(Linux)은 V4L2를 명시적으로 지정해야 안정적으로 잡히고, auto-exposure가
    수렴하지 못해 프레임이 새까맣게만 나오는 경우가 있어 그때는 수동 노출로
    재시도한다 (check_cameras.py에서 검증된 로직과 동일)."""
    if sys.platform == "win32":
        backends = [None, cv2.CAP_DSHOW]
        open_target: object = device_index
    else:
        backends = [cv2.CAP_V4L2, None]
        open_target = f"/dev/video{device_index}"

    for backend in backends:
        cap = cv2.VideoCapture(open_target, backend) if backend is not None else cv2.VideoCapture(open_target)
        try:
            if not cap.isOpened():
                continue

            if sys.platform != "win32":
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

            frame = _read_warmed_up_frame(cap)
            if frame is None:
                continue

            if sys.platform != "win32" and _mean_brightness(frame) < CAMERA_DARK_FRAME_THRESHOLD:
                manual_frame, manual_brightness = _try_manual_exposure(cap)
                if manual_frame is not None and manual_brightness > _mean_brightness(frame):
                    frame = manual_frame

            if _mean_brightness(frame) < CAMERA_DARK_FRAME_THRESHOLD:
                continue  # 이 백엔드로는 끝내 밝은 프레임을 못 얻음 -- 다음 백엔드 시도

            return frame
        finally:
            cap.release()

    raise RuntimeError(f"카메라에서 프레임을 읽지 못했습니다 (device_index={device_index}).")


def _capture_from_mock_dir(turn_id: int) -> np.ndarray:
    images = sorted(
        p for p in MOCK_IMAGE_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ) if MOCK_IMAGE_DIR.is_dir() else []
    if not images:
        raise RuntimeError(f"목업 이미지가 없습니다: {MOCK_IMAGE_DIR.resolve()}")
    image_path = images[turn_id % len(images)]
    frame = cv2.imread(str(image_path))
    if frame is None:
        raise RuntimeError(f"이미지를 읽지 못했습니다: {image_path}")
    return frame


def _crop_with_margin(image_rgb: np.ndarray, x1: float, y1: float, x2: float, y2: float):
    img_h, img_w = image_rgb.shape[:2]
    box_w, box_h = x2 - x1, y2 - y1
    margin_w, margin_h = box_w * MARGIN_RATIO, box_h * MARGIN_RATIO
    ex1 = int(max(0, x1 - margin_w))
    ey1 = int(max(0, y1 - margin_h))
    ex2 = int(min(img_w, x2 + margin_w))
    ey2 = int(min(img_h, y2 + margin_h))
    if ex2 <= ex1 or ey2 <= ey1:
        return None
    return image_rgb[ey1:ey2, ex1:ex2]


def _combine_final_label(number_pred: str, color_pred: str) -> str:
    """숫자/색상 분류기 중 하나라도 joker로 판단하면 joker로 확정."""
    if number_pred == "joker" or color_pred == "joker":
        return "joker"
    return f"{color_pred}_{number_pred}"


def analyze_frame(image_bgr: np.ndarray) -> tuple[list[dict], dict[str, float]]:
    """YOLO로 타일 위치를 찾고, 찾은 크롭 전체를 하나의 배치로 묶어 숫자/색상
    분류기를 각각 한 번씩만 호출한다 (크롭마다 forward를 따로 부르는 것보다
    최대 4배 이상 빠름 -- WORKLOG.md 12장 벤치마크 참고). (detections,
    {"yolo": 초, "classify": 초}) 형태로 반환한다."""
    if _yolo_model is None or _number_model is None or _color_model is None:
        raise RuntimeError("load_model()을 먼저 호출해야 합니다.")

    t0 = time.perf_counter()
    result = _yolo_model.predict(
        image_bgr,
        conf=YOLO_CONF,
        imgsz=YOLO_IMGSZ,
        device="cpu" if FORCE_CPU else (0 if torch.cuda.is_available() else "cpu"),
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
        batch = torch.stack([_eval_tf(Image.fromarray(c)) for c in crops]).to(DEVICE)
        with torch.no_grad():
            number_probs = torch.softmax(_number_model(batch), dim=1)
            color_probs = torch.softmax(_color_model(batch), dim=1)
        number_idx = number_probs.argmax(dim=1)
        color_idx = color_probs.argmax(dim=1)

        for i, (x1, y1, x2, y2, yolo_conf, yolo_cls_id) in enumerate(boxes_kept):
            number_pred = _number_classes[int(number_idx[i])]
            number_conf = float(number_probs[i, number_idx[i]])
            color_pred = _color_classes[int(color_idx[i])]
            color_conf = float(color_probs[i, color_idx[i]])
            final_label = _combine_final_label(number_pred, color_pred)
            confidence = min(number_conf, color_conf)

            if confidence < CONF_THRESHOLD:
                continue  # 임계값 미만인 결과는 버린다

            detections.append(
                {
                    "x1": float(x1), "y1": float(y1), "x2": float(x2), "y2": float(y2),
                    "yolo_class": _yolo_class_names[yolo_cls_id]
                    if yolo_cls_id < len(_yolo_class_names) else "?",
                    "yolo_conf": float(yolo_conf),
                    "number_pred": number_pred, "number_conf": number_conf,
                    "color_pred": color_pred, "color_conf": color_conf,
                    "final_label": final_label,
                    "confidence": confidence,
                }
            )
    classify_elapsed = time.perf_counter() - t0  # crop 추출 + 배치 분류 전체 포함

    return detections, {"yolo": yolo_elapsed, "classify": classify_elapsed}


def _rect_gap(a: dict, b: dict) -> float:
    """두 bbox 사이의 2D 최단거리. 겹치거나 닿아있으면 0."""
    dx = max(a["x1"] - b["x2"], b["x1"] - a["x2"], 0.0)
    dy = max(a["y1"] - b["y2"], b["y1"] - a["y2"], 0.0)
    return (dx ** 2 + dy ** 2) ** 0.5


def _find(parent: list[int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def _union(parent: list[int], i: int, j: int) -> None:
    ri, rj = _find(parent, i), _find(parent, j)
    if ri != rj:
        parent[ri] = rj


def _build_mst(detections: list[dict]) -> list[tuple[int, int, float]]:
    """전체 타일에 대한 최소 신장 트리(Prim's algorithm)를 만든다.
    간선 (u, v, weight)의 weight는 두 타일 bbox 사이의 2D 최단거리."""
    n = len(detections)
    in_tree = [False] * n
    dist = [float("inf")] * n
    parent = [-1] * n
    dist[0] = 0.0
    edges = []
    for _ in range(n):
        u = min((i for i in range(n) if not in_tree[i]), key=lambda i: dist[i])
        in_tree[u] = True
        if parent[u] != -1:
            edges.append((parent[u], u, dist[u]))
        for v in range(n):
            if not in_tree[v]:
                d = _rect_gap(detections[u], detections[v])
                if d < dist[v]:
                    dist[v] = d
                    parent[v] = u
    return edges


def _cluster_by_mst(detections: list[dict]) -> list[list[dict]]:
    """행(row)을 가정하지 않고, 전체 타일의 2D 거리 기반 최소 신장 트리(MST)를
    만든 뒤 "주변 간선들에 비해 유독 긴" 간선만 끊어서 그룹(멜드)을 나눈다
    (Zahn's inconsistent edge 알고리즘). 어떤 간선이 서로 다른 멜드를 잇는
    경계인지는 그 간선과 맞닿은 타일들 주변의 전형적인 간격과 비교해서
    판단하므로, 보드 전체에 걸쳐 밀집도가 다르거나 대각선으로 놓인 배치에서도
    각 지점이 스스로 기준을 잡는다."""
    n = len(detections)
    if n == 1:
        return [detections]

    avg_size = sum((d["x2"] - d["x1"] + d["y2"] - d["y1"]) / 2 for d in detections) / n
    min_gap_floor = avg_size * MIN_SPLIT_GAP_RATIO

    edges = _build_mst(detections)
    # 노드별로 인접한 간선의 인덱스를 모아둔다 (가중치가 아니라 인덱스로 저장해야
    # 가중치가 우연히 같은 다른 간선까지 "자기 자신"으로 착각해 제외하지 않는다).
    adjacent_edge_idx: dict[int, list[int]] = {i: [] for i in range(n)}
    for idx, (u, v, _w) in enumerate(edges):
        adjacent_edge_idx[u].append(idx)
        adjacent_edge_idx[v].append(idx)

    parent = list(range(n))
    for idx, (u, v, w) in enumerate(edges):
        neighbor_idx = set(adjacent_edge_idx[u] + adjacent_edge_idx[v]) - {idx}
        neighbor_weights = [edges[k][2] for k in neighbor_idx]
        local_avg = sum(neighbor_weights) / len(neighbor_weights) if neighbor_weights else 0.0
        cut_threshold = max(local_avg * INCONSISTENT_EDGE_RATIO, min_gap_floor)
        if w <= cut_threshold:
            _union(parent, u, v)

    clusters: dict[int, list[dict]] = {}
    for i in range(n):
        clusters.setdefault(_find(parent, i), []).append(detections[i])
    return list(clusters.values())


def _same_row(a: dict, b: dict) -> bool:
    """두 bbox의 y축 겹침이 더 작은 쪽 높이의 ROW_OVERLAP_RATIO 이상이면 같은 행으로 본다."""
    overlap = min(a["y2"], b["y2"]) - max(a["y1"], b["y1"])
    if overlap <= 0:
        return False
    min_height = min(a["y2"] - a["y1"], b["y2"] - b["y1"])
    return overlap >= min_height * ROW_OVERLAP_RATIO


def _split_into_rows(members: list[dict]) -> list[list[dict]]:
    """y축 겹침만 보고(x 거리는 무시) 같은 행끼리 묶는다. _semantic_resplit이
    x축 순서 DP를 시도하기 전에, 서로 다른 행이 x 순서상 뒤섞여서 DP가 못
    찾는 걸 막기 위한 전처리 단계."""
    n = len(members)
    parent = list(range(n))
    for i in range(n):
        for j in range(i + 1, n):
            if _same_row(members[i], members[j]):
                _union(parent, i, j)
    rows: dict[int, list[dict]] = {}
    for i in range(n):
        rows.setdefault(_find(parent, i), []).append(members[i])
    return list(rows.values())


def _split_by_x_order(members: list[dict]) -> list[list[dict]]:
    """같은 x축 순서를 유지한 채(물리적 배치 순서를 신뢰) 연속 구간으로 나누어서
    각 구간이 전부 유효한 멜드가 되는 분할이 있는지 찾는다 (word-break류 DP)."""
    ordered = sorted(members, key=lambda m: m["x1"])
    n = len(ordered)
    dp: list[list[list[dict]] | None] = [None] * (n + 1)
    dp[0] = []
    for i in range(1, n + 1):
        for j in range(max(0, i - MAX_MELD_SIZE), i - 2):  # 후보 멜드는 최소 3장
            if dp[j] is None:
                continue
            candidate = ordered[j:i]
            if validate_group([m["final_label"] for m in candidate]).valid:
                dp[i] = dp[j] + [candidate]
                break
    return dp[n] if dp[n] is not None else [members]


def _semantic_resplit(members: list[dict]) -> list[list[dict]]:
    """기하학적으로 하나로 묶인 그룹이 rules상 유효한 멜드가 아니면, 이미 알고
    있는 타일 라벨(색상+숫자)만으로 다시 나눌 수 있는지 찾는다. 먼저 행(row)
    단위로 나눠보고(위/아래로 다른 줄에 놓인 멜드가 섞인 경우), 그래도 안 되면
    같은 행 안에서 x축 순서 기준으로 나눠본다. 새로운 게임 규칙을 만드는 게
    아니라 rules.validate_group을 그대로 재사용해서 판단한다.
    타일이 대각선으로 겹쳐 놓여서 실제 멜드가 행으로도 x축 순서로도 분리되지
    않는 경우는 이 방식으로 못 찾는다 -- 그때는 원래 그룹을 그대로 반환한다
    (기하 정보만으로는 원천적으로 구분 불가능한 경우)."""
    labels = [m["final_label"] for m in members]
    if validate_group(labels).valid:
        return [members]
    if len(members) > SEMANTIC_SPLIT_MAX_TILES:
        return [members]

    row_groups = _split_into_rows(members)
    if len(row_groups) > 1:
        result = []
        for row_members in row_groups:
            result.extend(_semantic_resplit(row_members))
        if all(validate_group([m["final_label"] for m in g]).valid for g in result):
            return result
        # 행 분할로도 전부 유효해지지 않으면 원래 x축 순서 DP로 폴백.

    return _split_by_x_order(members)


def _order_run_members(members: list[dict]) -> list[dict]:
    """그룹이 유효한 런이면, rules.order_run_labels()가 정한 숫자 오름차순(조커는
    자신이 채우는 자리)에 맞춰 members 자체를 재정렬해서 반환한다. 런이 아니거나
    (세트/무효 그룹) 정렬이 불필요하면 원래 순서를 그대로 반환한다. 지금까지는
    grouping 단계의 물리적 좌표(x축) 순서를 그대로 최종 결과(tiles/labels)에
    썼는데, 조커가 껴 있으면 그게 숫자 순서와 어긋나 보이는 문제가 있었다."""
    labels = [m["final_label"] for m in members]
    ordered_labels = order_run_labels(labels)
    if ordered_labels == labels:
        return members

    remaining = list(members)
    joker_members = iter(m for m in remaining if m["final_label"] == "joker")
    number_to_member = {m["final_label"]: m for m in remaining if m["final_label"] != "joker"}

    return [
        next(joker_members) if label == "joker" else number_to_member[label]
        for label in ordered_labels
    ]


def group_detections(detections: list[dict]) -> list[dict]:
    """1단계로 MST 기반 지역 적응형 클러스터링(_cluster_by_mst)으로 타일을
    묶고, 2단계로 그렇게 묶인 그룹이 유효한 멜드가 아니면 라벨 정보를 이용해
    다시 나눌 수 있는지 시도한다(_semantic_resplit). 유효한 런이면 결과의
    tiles/labels 순서를 숫자 오름차순(조커는 채우는 자리)으로 재정렬한다
    (_order_run_members). 각 그룹은 bbox(구성원 전체를 감싸는 박스)와
    결과값(final_label 목록)을 갖는다."""
    if not detections:
        return []

    clusters = _cluster_by_mst(detections)

    ordered_groups = []
    for members in clusters:
        for group_members in _semantic_resplit(members):
            ordered_groups.append(_order_run_members(group_members))
    ordered_groups.sort(key=lambda members: min(d["x1"] for d in members))

    result = []
    for i, members in enumerate(ordered_groups):
        result.append(
            {
                "group_id": i,
                "bbox": {
                    "x1": min(m["x1"] for m in members),
                    "y1": min(m["y1"] for m in members),
                    "x2": max(m["x2"] for m in members),
                    "y2": max(m["y2"] for m in members),
                },
                "tiles": [
                    {
                        "bbox": {"x1": m["x1"], "y1": m["y1"], "x2": m["x2"], "y2": m["y2"]},
                        "label": m["final_label"],
                        "confidence": m["confidence"],
                    }
                    for m in members
                ],
                "labels": [m["final_label"] for m in members],
            }
        )
    return result


def judge_groups(groups: list[dict], state: dict) -> tuple[str, list[str], list[dict]]:
    """각 그룹이 런(run) 또는 세트(set)로 유효한지 rules.py로 검증한다.
    그룹 하나라도 무효면 전체 FAIL, 무효 사유들을 reason_codes에 모아 반환한다.
    어느 그룹이 왜 무효인지는 invalid_groups(그룹별 group_id/reason_code)로
    따로 반환한다 -- reason_codes만으로는 "어느 그룹이 문제인지" 알 수 없어서
    (mqtt_handler.py의 VIOLATION_CODE_MAP 등 기존 소비자와의 호환을 위해
    reason_codes 자체의 평면 리스트 형태는 그대로 유지).

    이 플레이어(state["current_player_id"])가 아직 초기 멜드(30점)를 못 냈으면,
    직전 턴 보드(state["last_board_labels"])와 비교해서 새로 낸 그룹들의 점수를
    확인한다. 통과하면 이후 턴부터는 이 플레이어를 다시 검사하지 않는다.
    DEMO_SKIP_INITIAL_MELD=true면 이 검사 자체를 건너뛴다 (시연용)."""
    reason_codes = []
    invalid_groups = []
    for group in groups:
        result = validate_group(group["labels"])
        if not result.valid:
            reason_codes.append(result.reason_code)
            invalid_groups.append({"group_id": group["group_id"], "reason_code": result.reason_code})

    player_id = state["current_player_id"]
    if not DEMO_SKIP_INITIAL_MELD and not state["has_completed_initial_meld"].get(player_id, False):
        new_groups = find_new_groups(groups, state.get("last_board_labels", []))
        if new_groups:  # 새 그룹이 없으면 멜드 시도 자체가 없었던 턴(덱에서 타일만 가져옴) -- 반칙 아님
            meld_ok, _score = validate_initial_meld(new_groups)
            if meld_ok:
                state["has_completed_initial_meld"][player_id] = True
            else:
                reason_codes.append("INVALID_INITIAL_MELD")
                # 초기 멜드 미달은 그룹 하나가 아니라 이번 턴에 새로 낸 그룹 전체에 걸친
                # 문제라서, 특정 group_id 하나로 못 좁히고 새 그룹들의 id를 전부 붙인다.
                for g in new_groups:
                    invalid_groups.append({"group_id": g["group_id"], "reason_code": "INVALID_INITIAL_MELD"})

    decision = "FAIL" if reason_codes else "PASS"
    return decision, reason_codes, invalid_groups


def _build_display(decision: str, reason_codes: list[str], invalid_groups: list[dict] | None = None) -> dict:
    if decision == "PASS":
        return {
            "screen": "TURN_RESULT",
            "title": "정상적인 조합입니다.",
            "message": None,
            "severity": "info",
        }
    if invalid_groups:
        message = ", ".join(f"group {g['group_id']}: {g['reason_code']}" for g in invalid_groups)
    else:
        message = ", ".join(reason_codes) or None
    return {
        "screen": "TURN_RESULT",
        "title": "잘못된 조합입니다.",
        "message": message,
        "severity": "error",
    }


def run_turn(state: dict, turn_id: int) -> dict:
    """analyze-turn 엔드포인트가 호출하는 진입점: 촬영 -> 분석 -> 판정 -> 로그까지 한 번에.

    state는 main.py/state.py가 들고 있는 게임 상태 dict를 그대로 받는다 (game_id,
    current_player_id, recheck_count, game_log 키가 있다고 가정). 로그는 저장/전송 없이
    print만 한다 -- 파일/DB/콜백 연동은 나중에 필요해지면 추가.

    매 호출마다 load_model() -> ... -> unload_model()로 GPU를 잠깐만 점유한다 (팀원
    서비스와 같은 Jetson을 공유하기 때문 -- 위 전역 변수 주석 참고).

    load_model/capture/yolo/classify/group/judge/unload_model/total 단계별
    소요 시간을 측정해서 응답의 "timings_ms" 필드로 함께 반환한다 -- 실제 보드에서
    어느 단계가 병목인지 바로 관찰하기 위한 용도 (WORKLOG.md 13~14장 참고).
    """
    timings: dict[str, float] = {}
    t_total0 = time.perf_counter()

    t0 = time.perf_counter()
    load_model()
    timings["load_model"] = time.perf_counter() - t0

    try:
        t0 = time.perf_counter()
        frame = capture_frame(turn_id)
        timings["capture"] = time.perf_counter() - t0

        detections, stage_timings = analyze_frame(frame)
        timings.update(stage_timings)

        t0 = time.perf_counter()
        groups = group_detections(detections)
        timings["group"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        decision, reason_codes, invalid_groups = judge_groups(groups, state)
        timings["judge"] = time.perf_counter() - t0
    finally:
        t0 = time.perf_counter()
        unload_model()
        timings["unload_model"] = time.perf_counter() - t0

    timings["total"] = time.perf_counter() - t_total0
    timings_ms = {k: round(v * 1000, 2) for k, v in timings.items()}

    # 반칙(FAIL) 턴은 상태에 반영하지 않는다 -- 무효 처리된 시도가 다음 턴의 diff
    # 기준점(last_board_labels)이나 이력(game_log)에 남으면, 플레이어가 다시 시도할 때
    # "이미 있던 타일"로 잘못 취급되어 초기 멜드 재판정이 꼬인다. PASS일 때만 저장.
    if decision == "PASS":
        state["last_board_labels"] = [label for g in groups for label in g["labels"]]

        turn_record = {
            "turn_id": turn_id,
            "player_id": state["current_player_id"],
            "decision": decision,
            "reason_codes": reason_codes,
        }
        state["game_log"].append(turn_record)

    log = {
        "player_id": state["current_player_id"],
        "recheck_count": state.get("recheck_count", 0),
        "groups": groups,
        "image_reference": None,  # 이미지 저장을 안 하므로 항상 None
    }

    response = {
        "request_id": state.get("last_request_id"),
        "game_id": state["game_id"],
        "turn_id": turn_id,
        "decision": decision,
        "reason_codes": reason_codes,
        "invalid_groups": invalid_groups,
        "display": _build_display(decision, reason_codes, invalid_groups),
        "log": log,
        "game_log": state["game_log"],
        "timings_ms": timings_ms,
    }

    print(f"[facilitator] turn_id={turn_id} player={log['player_id']} decision={decision} "
          f"reason_codes={reason_codes} detections={len(detections)} groups={len(groups)}")
    print("  timings(ms): " + ", ".join(f"{k}={v:.2f}" for k, v in timings_ms.items()))
    for g in groups:
        b = g["bbox"]
        print(f"  group {g['group_id']}: bbox=({b['x1']:.0f},{b['y1']:.0f})-({b['x2']:.0f},{b['y2']:.0f}) "
              f"labels={g['labels']}")

    return response


if __name__ == "__main__":
    # image/ 폴더의 이미지로 파이프라인을 바로 테스트한다.
    # 카메라 없이 돌리려면 .env에서 CAMERA_ENABLED=false로 맞춰두고 실행할 것.
    if CAMERA_ENABLED:
        print("CAMERA_ENABLED=true 상태입니다 -- image/ 폴더 대신 실제 카메라로 촬영합니다. "
              "폴더 이미지로 테스트하려면 .env에서 CAMERA_ENABLED=false로 바꾸세요.")

    # load_model()은 이제 run_turn() 안에서 매번 알아서 호출/해제된다 (여기서 미리 안 부름).

    test_state = {
        "game_id": "test-game",
        "current_player_id": "player_1",
        "recheck_count": 0,
        "game_log": [],
        "last_request_id": "req-test",
        "last_board_labels": [],
        "has_completed_initial_meld": {},
    }

    image_count = len(
        [p for p in MOCK_IMAGE_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
    ) if MOCK_IMAGE_DIR.is_dir() else 0
    if image_count == 0 and not CAMERA_ENABLED:
        raise SystemExit(f"테스트할 이미지가 없습니다: {MOCK_IMAGE_DIR.resolve()}")

    turn_count = image_count if not CAMERA_ENABLED else 1
    for turn_id in range(1, turn_count + 1):
        response = run_turn(test_state, turn_id)
        print(response)
