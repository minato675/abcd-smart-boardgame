#!/bin/bash
# Jetson에서 mc/ 파이썬 패키지를 설치하는 스크립트.
#
# torch는 NVIDIA가 Jetson용으로 커스텀 빌드한 로컬 wheel을 쓰는데, 버전 문자열이
# "2.5.0a0+872d972e41.nv24.08...."라서 PyPI torchvision==0.20.0이 요구하는
# "torch==2.5.0"과 문자열이 달라 pip 의존성 검사에서 충돌(ResolutionImpossible)이 난다.
# 실제로는 호환되는 조합이라, torchvision만 --no-deps로 설치해서 이 검사를 건너뛴다.
#
# 사용법: mc/ 안에서 ./install_jetson.sh

set -e
cd "$(dirname "$0")"

TORCH_WHEEL="torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl"

if [ ! -f "$TORCH_WHEEL" ]; then
    echo "torch wheel을 찾을 수 없습니다: $(pwd)/$TORCH_WHEEL"
    exit 1
fi

pip install "./$TORCH_WHEEL"
pip install torchvision==0.20.0 --no-deps
pip install ultralytics opencv-python numpy Pillow python-dotenv "paho-mqtt<2.0"

echo "설치 완료"
