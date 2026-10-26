# Jetson 환경 세팅 가이드

`install_jetson.sh`는 파이썬 패키지(pip)만 설치합니다. 그 외에 새 Jetson이나
새 환경에서 필요한 시스템 레벨 설치/장치별 설정은 이 문서에 정리합니다.

## 1. 파이썬 패키지 설치 (pip)

```bash
cd table/mc
python3 -m venv .venv
source .venv/bin/activate
./install_jetson.sh
```

torch wheel(`torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl`)은
git에 커밋돼 있어서 `git pull`로 같이 받아집니다. torchvision은 PyPI(`torchvision==0.20.0`)에서
받되, torch의 커스텀 버전 문자열 때문에 의존성 검사가 충돌해서 `--no-deps`로 설치합니다
(실제로는 호환되는 조합).

## 2. 시스템 레벨 설치 (sudo apt)

파이썬 가상환경과 무관하게 시스템에 직접 설치해야 하는 것들:

```bash
sudo apt install v4l-utils   # v4l2-ctl -- 카메라 장치 디버깅/직접 캡처 테스트용
```

## 3. 카메라 장치별 설정 (`.env`)

**`CAMERA_DEVICE_INDEX`는 장치마다 다를 수 있어서 자동화 대상이 아닙니다.** 카메라가
안 잡히거나 새 장치로 바뀌면 아래 순서로 확인:

```bash
v4l2-ctl --list-devices          # 연결된 카메라와 /dev/videoN 노드 확인
v4l2-ctl -d /dev/video0 --all    # Video Capture인지 Metadata Capture인지 확인
```

**주의**: USB 캡처 카드 하나가 보통 `/dev/video0`(실제 영상, Video Capture)과
`/dev/video1`(메타데이터 전용, Metadata Capture) 두 노드로 잡힙니다. `.env`의
`CAMERA_DEVICE_INDEX`를 메타데이터 노드로 잘못 잡으면:
1. 그 노드는 프레임을 못 줘서 V4L2 실패 → GStreamer 백엔드로 폴백 시도
2. 이 실패한 GStreamer 시도가 같은 프로세스 안의 상태를 오염시켜서
3. 그 다음 시도하는 정상 노드(`/dev/video0`)까지 같이 실패

즉 **엉뚱한 인덱스를 먼저 건드리면 정상 인덱스까지 도미노로 실패**합니다. 실제 `Video Capture`
Capability를 가진 노드를 `CAMERA_DEVICE_INDEX`로 지정하세요.

`CAMERA_WARMUP_FRAMES`(기본 15)도 장치마다 필요한 최소값이 다릅니다 — auto-exposure가
수렴하기 전 프레임은 어둡게 나와서 버려집니다. 너무 낮으면 촬영 자체가 실패할 수 있습니다
(실측: 이 카메라는 3으로는 실패, 5부터 성공).

## 4. YOLO/분류 임계값 (`.env`)

`YOLO_CONF`가 `.env`에 없으면 `pipeline.py` 기본값 0.25로 낮게 동작해서, NMS가 겹치는
박스 두 개를 못 합쳐 **같은 타일이 중복 탐지**되는 문제가 생깁니다(예: `blue_6`가 그룹
안에 2번 나타남). PC 테스트에서 검증된 조합:

```
YOLO_CONF=0.7
CONF_THRESHOLD=0.7
```

## 5. MQTT

`paho-mqtt`(파이썬 클라이언트)는 `install_jetson.sh`에 포함돼 있어 별도 설치가 필요
없습니다. MQTT 브로커(mosquitto 등)를 Jetson에 직접 띄우는 경우엔 별도로
`sudo apt install mosquitto`가 필요합니다(브로커를 어디서 운영하는지에 따라 다름).
