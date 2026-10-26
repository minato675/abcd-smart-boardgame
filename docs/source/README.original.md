# 스마트 보드게임 카페

태블릿, AI, RFID 스마트 보관함을 연동해 보드게임의 검색부터 대여·반납, 규칙 안내와 플레이 보조까지 제공하는 통합 프로젝트입니다.

## 기술 스택

**Frontend**

![Vue][vue] ![TypeScript][typescript] ![Vite][vite] ![Tailwind CSS][tailwind]

**Backend & Data**

![Java][java] ![Spring Boot][spring] ![Gradle][gradle] ![MyBatis][mybatis] ![PostgreSQL][postgresql] ![Qdrant][qdrant]

**AI & Voice**

![Python][python] ![PyTorch][pytorch] ![YOLO][yolo] ![OpenCV][opencv] ![ONNX][onnx] ![Gemini][gemini] ![ElevenLabs][elevenlabs]

**IoT & Infra**

![C++][cplusplus] ![CMake][cmake] ![Arduino][arduino] ![Raspberry Pi][raspberrypi] ![MQTT][mqtt] ![Mosquitto][mosquitto] ![Docker][docker] ![Nginx][nginx] ![Jenkins][jenkins]

**3D Design & Fabrication**

![Bambu Lab][bambulab] ![FDM 3D Printing][printing3d] ![3D CAD][cad3d]

## 주요 기능

- 보드게임 검색, 상세 조회, 대여 및 예약
- 방 입·퇴실과 대여·재고 관리
- 음성 기반 보드게임 규칙 QnA
- 카메라 기반 루미큐브 턴 분석 및 반칙 감지
- RFID 카드와 스마트 보관함을 이용한 대여·반납
- 관리자용 운영 현황 및 통계 화면

## 시스템 구성

```text
태블릿(Vue) ── REST ── Spring Boot ── PostgreSQL
     │                     │
     └──── MQTT ───────────┼──── Jetson(AI·음성)
                           └──── Raspberry Pi ── Arduino 보관함
```

| 경로 | 설명 | 주요 기술 |
| --- | --- | --- |
| `boardgame-frontend` | 손님용 태블릿 및 관리자 화면 | Vue 3, TypeScript, Vite |
| `inte-server` | REST API, DB 및 MQTT 통합 서버 | Java 21, Spring Boot, MyBatis |
| `table/mc` | 루미큐브 AI 심판 | Python, YOLO, PyTorch, OpenCV |
| `table/qna-server` | 음성 규칙 QnA | Python, Gemini, TTS |
| `table/wakeword` | 호출어 감지 | Python, ONNX Runtime, openWakeWord |
| `cabinet/controller` | RFID 및 보관함 통합 제어 | C++, MQTT, Bluetooth RFCOMM |
| `cabinet/unit` | 개별 보관함 펌웨어 | Arduino, Adafruit NeoPixel |
| `exec` | 배포 및 DB 초기화 자료 | Docker Compose, Nginx, PostgreSQL |

## 빠른 실행

### 프런트엔드

```bash
cd boardgame-frontend
npm install
npm run dev
```

기본 개발 주소는 `http://localhost:5173`이며, 통합 서버가 함께 실행되어야 합니다.

### 통합 서버

```bash
cd inte-server
./gradlew bootRun
```

기본 포트는 `8111`입니다. PostgreSQL과 MQTT 접속 정보는 환경에 맞게 설정해야 합니다.

### 전체 배포

Docker, Jetson, Raspberry Pi 및 Arduino 설정은 [포팅 매뉴얼](exec/포팅%20매뉴얼.md)을 참고하세요.

> API 키와 비밀번호는 저장소에 직접 작성하지 말고 환경변수 또는 별도의 비밀 저장소로 관리합니다.

## 주요 문서

- [프런트엔드 안내](boardgame-frontend/README.md)
- [규칙 QnA 안내](table/qna-server/README.md)
- [Wake Word 안내](table/wakeword/README.md)
- [Raspberry Pi 보관함 컨트롤러](cabinet/controller/README.md)
- [Arduino 보관함 유닛](cabinet/unit/README.md)
- [포팅 매뉴얼](exec/포팅%20매뉴얼.md)

## 팀원 및 기술 스택

| 이름 | 담당 영역 | 주요 기술 및 도구 | 주요 기여 |
| --- | --- | --- | --- |
| 박건우 | IoT / AI |  |  |
| 김지호 | IoT / 3D Design & Fabrication| ![C++][cplusplus] ![Arduino][arduino] ![CMake][cmake] ![Bambu Lab][bambulab] ![FDM 3D Printing][printing3d] ![3D CAD][cad3d]| 사물함 회로 설계 및 전체 구현 , 카메라 지지대 3D 프린팅 진행 |
| 김형수 | AI | ![Python][python] ![MQTT][mqtt] ![YOLO][yolo] ![OpenCV][opencv] | 루미큐브 mc 기능 구현 |
| 박준서 | Infra / FE / BE |  |  |
| 임다빈 | AI | ![Python][python] ![Gemini][gemini] ![ElevenLabs][elevenlabs] ![MQTT][mqtt] | 루미큐브 타일 데이터 라벨링 및 모델 학습/검증<br/>음성 QnA 서버 구현 및 AI/TTS 연동<br/>MQTT 기반 QnA 흐름 구현 및 중복 실행 방어 |

## 회고

### 박건우
이번 프로젝트에서 나는 테이블의 음성 인식과 RFID 기반 사물함 제어를 맡았다. 사용자가 “싸피야”라고 부르면 QnA를 시작하고 “내 턴 끝났어”라고 말하면 게임 분석을 시작하는 wake word 서비스를 만들었다. 카드가 인식되면 필요한 사물함을 열어 주는 컨트롤러도 함께 개발했다.
Wake word는 처음에 모델 파일만 연결하면 금방 끝날 줄 알았다. 실제로는 그렇지 않았다. 모델이 마이크의 음성 데이터를 바로 받는 구조가 아니어서 오디오를 알맞은 형식으로 변환하고 openWakeWord의 전처리 과정을 거쳐야 했다. 마이크 입력과 모델 추론이 동시에 꼬이지 않도록 추론 작업도 하나의 worker에서 처리하게 만들었다.
음성을 계속 듣는 것만으로는 서비스에 사용할 수 없었다. 서버에서 듣기 시작과 중지를 제어할 수 있도록 MQTT를 연결했고 현재 상태도 확인할 수 있게 했다. 네트워크가 끊기거나 마이크를 찾지 못했을 때 계속 정상인 것처럼 동작하지 않도록 상태 전이와 오류 처리도 넣었다. 실제 마이크가 없어도 확인할 수 있는 replay 기능과 테스트를 만들었고 Jetson에서 USB 마이크를 이용해 실행할 수 있는 launcher도 작성했다.
이 과정에서 기능이 동작한다는 것과 실제로 사용할 수 있다는 것은 다르다는 걸 배웠다. 준비된 음성 파일에서는 두 문장이 모두 인식됐지만 그 결과만으로 정확도가 충분하다고 말할 수는 없었다. 사람마다 발음이 다르고 주변 소음이나 스피커 출력에도 영향을 받기 때문이다. 그래서 모델 검증 결과가 기준을 통과하지 못한 상태에서는 운영용으로 실행되지 않도록 제한했다. 코드를 완성했다고 모델 품질까지 완성된 것은 아니었다.
RFID 리더기도 바로 가져다 쓸 만한 라이브러리가 없어서 C SDK부터 만들었다. 이후 C++과 Python에서도 사용할 수 있게 확장했고 반복해서 장치를 확인하는 방식 대신 이벤트가 들어왔을 때 처리하도록 개선했다. 장치 경로를 쉽게 찾도록 설정을 추가하고 실제 장비가 없어도 검증할 수 있도록 파서와 테스트도 따로 작성했다.
가장 많은 시간이 들어간 부분은 캐비닛 컨트롤러였다. Bluetooth 장치를 검색하고 등록하는 기능부터 RFCOMM 통신, 연결 시간 초과, 재연결, 여러 캐비닛 관리까지 하나씩 구현했다. 처음에는 Arduino 코드에 캐비닛 번호를 고정했지만 장치가 늘어나면 관리가 어려워져 컨트롤러가 캐비닛 정보를 관리하도록 바꿨다. 문이 실제로 열리고 닫혔는지와 통신 중 어떤 오류가 발생했는지도 MQTT를 통해 서버에 전달하도록 했다.
개발 과정에서 Bluetooth 컨트롤러를 master에 병합했다가 다시 되돌린 적도 있다. 기능을 많이 넣는 데 집중하다 보니 다른 기능과 합쳤을 때 구조가 지나치게 커졌다. 만든 코드를 되돌리는 게 아깝기는 했지만 필요한 흐름부터 다시 정리하고 작은 상태 머신을 중심으로 구현했다. 이 경험을 통해 기능을 많이 만드는 것보다 팀이 이해하고 실제로 사용할 수 있는 구조를 만드는 일이 더 중요하다는 걸 느꼈다.
하드웨어를 항상 연결해 놓고 개발할 수 없어서 MQTT 테스트 도구와 mock server도 만들었다. 카드 인식부터 반납 사물함 열기, 문 닫힘 확인, 다음 사물함 열기까지의 과정을 장비 없이 재현했다. 처음에는 이런 도구를 부가 작업이라고 생각했지만 문제가 생겼을 때 원인이 서버인지 컨트롤러인지 장치인지 구분하려면 꼭 필요했다. 설치 스크립트와 systemd 서비스, 장비 점검 절차를 작성한 것도 같은 이유였다.
후반에는 내가 만든 wake word와 캐비닛 컨트롤러를 팀원들이 만든 MC, QnA 서버, 프론트엔드 기능과 연결했다. 각 기능이 따로 실행될 때는 괜찮았지만 한꺼번에 붙이면 MQTT 메시지 순서나 실행 시점 때문에 새로운 문제가 생겼다. 내 코드만 잘 실행되게 만드는 것보다 전체 흐름에서 언제 시작하고 멈춰야 하는지 팀원들과 맞추는 일이 중요했다.
다시 시작한다면 MQTT 규격과 상태 변화를 먼저 확정하고 mock 환경부터 만들 것 같다. 큰 기능을 완성한 뒤 한꺼번에 병합하지 않고 작은 단위로 자주 통합해 볼 것이다. 이번 프로젝트를 통해 음성 모델과 하드웨어를 서비스에 연결하는 과정 전체를 경험했다. 특히 정상적으로 동작하는 경우보다 연결이 끊기거나 잘못된 입력이 들어왔을 때 어떻게 버틸지를 먼저 생각해야 한다는 점이 가장 크게 남았다.

### 김지호
6주라는 시간이 생각보다 빠르게 지나가면서, 처음 계획했던 기능들을 모두 구현하지 못한 점은 아쉬움으로 남습니다. 하지만 제한된 시간 안에서 팀원들과 함께 하나의 결과물을 완성했다는 점에서 의미 있는 경험이었습니다.

특히 이번 프로젝트를 통해 임베디드 개발에 처음 도전했습니다. 비전공자로서 회로에 대한 지식이 거의 없는 상태에서 시작했기 때문에 부품을 연결하고 회로를 설계하는 모든 과정이 낯설고 어려웠습니다. 하지만 GPT를 활용해 부족한 개념을 확인하고, 개인적으로 회로와 부품의 작동 원리를 공부하면서 하나씩 문제를 해결해 나갔습니다. 시행착오 끝에 설계한 회로가 실제로 작동하고, RFID 태그와 문 센서, 잠금장치, LED가 연동되는 모습을 처음 확인했을 때는 신기함과 함께 큰 성취감을 느꼈습니다.

이번 프로젝트는 단순히 결과물을 만드는 것을 넘어, 익숙하지 않은 분야도 직접 부딪히고 공부하면 구현할 수 있다는 자신감을 얻게 해준 경험이었습니다. 처음에는 회로도를 보는 것조차 어려웠지만, 프로젝트가 끝날 무렵에는 직접 회로를 구성하고 문제의 원인을 찾아 수정할 수 있을 만큼 성장할 수 있었습니다.

무엇보다 부족하고 어려운 순간에도 끝까지 함께해 준 팀원들에게 고맙다는 말을 전하고 싶습니다. 각자의 역할을 책임감 있게 수행하고 서로의 부족한 부분을 채워주었기에 프로젝트를 끝까지 완성할 수 있었습니다. 구현하지 못한 기능에 대한 아쉬움은 남지만, 팀원들과 함께 고민하고 문제를 해결했던 6주는 앞으로 새로운 분야에 도전할 때 큰 자산이 될 것 같습니다.
### 김형수
루미큐브 보드를 카메라로 찍으면 반칙 여부를 자동으로 판정해주는 AI 진행자(mc)를 맡았습니다. 타일 탐지, 숫자·색상 분류, 그룹핑, 규칙 판정까지 이어지는 파이프라인 전체를 설계하고 구현했습니다.

가장 오래 걸린 건 모델 학습 데이터 수집과 학습이었습니다. 실제 카메라로 찍은 보드 사진을 모으고, 타일 라벨(숫자·색상·조커)과 그룹 경계를 사람이 직접 검수해서 정답 데이터를 만들었고, 탐지기와 분류기를 여러 모델로 각각 학습시켜 비교했습니다. 임계값 하나 바꾸는 데도 결과가 크게 달라져서, 수치를 보며 값을 조정하고 다시 학습·검증하는 과정을 여러 차례 반복해야 했습니다.

그룹핑 로직도 까다로운 문제였습니다. 서로 다른 멜드가 하나로 잘못 합쳐지는 문제를 고치려고 알고리즘을 세 번 다시 설계했는데, 그 과정에서 그룹핑이 실패하면 정상적으로 낸 조합이 그대로 반칙으로 포함되어 전달된다는 걸 알게 됐습니다. 이후 복구 기능을 추가하여 보조하였습니다.

알고리즘 기반 기능과 AI 기반 기능을 함께 진행하면서 개발 방식의 차이도 느꼈습니다. 그룹핑 로직은 코드를 고치고 바로 결과를 눈으로 확인할 수 있어서 반복 속도는 빨랐지만, 체인 중간에 낀 그룹이나 낱장 타일 같은 예외 상황을 하나씩 조건문으로 처리하다 보니 로직이 점점 꼬이고 복잡해지는 문제가 있었습니다. 반면 AI 모델은 데이터를 다시 모으고 학습시키는 데 시간이 오래 걸렸지만, 한 번 잘 학습시켜두면 개별 예외 상황을 일일이 조건문으로 추가하지 않아도 데이터 자체가 그런 변형들을 흡수하기에 차이를 느꼈습니다.

마지막으로 제대로 된 하나를 만들려고 했는데, 그래도 조금 더 욕심을 내서 다양한 게임을 추가했으면 좋았겠다는 아쉬움이 남습니다.

### 박준서
xxx
### 임다빈
이번 프로젝트에서 처음으로 AI 파트를 담당하며, AI 기능은 모델을 학습시키는 것만큼이나 학습에 사용할 데이터셋을 잘 준비하는 과정이 중요하다는 것을 배웠습니다. 루미큐브 타일 인식 모델을 준비하면서 숫자, 색상, 조커처럼 구분해야 할 기준을 명확히 잡아야 했고, 라벨링 기준이 조금만 흔들려도 모델 결과에 영향을 줄 수 있다는 점을 경험했습니다. 또한 실제 카메라 환경에서는 조명, 각도, 그림자, 타일 배치 같은 변수가 많아 학습 데이터와 테스트 환경을 현실에 가깝게 설계하는 것이 중요하다는 것을 알게 되었습니다.
최종적으로 제가 학습시킨 모델이 실제 서비스에 선정되지는 못해 아쉬움이 남았습니다. 하지만 이 과정을 통해 단순히 학습을 완료하는 것보다, 팀이 실제로 사용할 수 있을 만큼 안정적인 데이터와 검증 결과를 만드는 것이 더 중요하다는 점을 배웠습니다.

이후 담당한 QnA 서버에서는 AI 모델을 직접 학습시키는 것과는 다른 방식의 AI 활용을 경험했습니다. 처음에는 음성을 STT로 변환한 뒤 LLM에 전달하는 구조를 생각했지만, 실제 통합 과정에서는 STT 빈값, 마이크 점유, MQTT 중복 이벤트, TTS 지연처럼 서비스 흐름에서 발생하는 문제가 더 중요하게 다가왔습니다. 
이를 해결하기 위해 음성과 룰북 context를 함께 처리하는 Gemini Audio Direct 구조로 변경했고, qna/res와 TTS 첫 chunk를 기준으로 사용자가 체감하는 응답 시간을 다시 정의했습니다.
QnA 서버를 구현하면서 AI API를 호출하는 것만으로는 서비스 기능이 완성되지 않는다는 것을 배웠습니다. 입력이 안정적으로 들어오고, 모듈 간 이벤트 순서가 명확하며, 실패 상황에서도 다음 흐름이 막히지 않아야 실제 사용자가 쓸 수 있는 기능이 된다는 점을 경험했습니다. 
이번 프로젝트를 통해 모델 학습과 AI API 연동을 모두 경험하며, AI 기능을 실제 서비스 안에서 안정적으로 동작하게 만드는 전체 흐름을 이해할 수 있었습니다.

[vue]: https://img.shields.io/badge/Vue.js-3.5-4FC08D?style=flat-square&logo=vuedotjs&logoColor=white
[typescript]: https://img.shields.io/badge/TypeScript-6.0-3178C6?style=flat-square&logo=typescript&logoColor=white
[vite]: https://img.shields.io/badge/Vite-8.1-646CFF?style=flat-square&logo=vite&logoColor=white
[tailwind]: https://img.shields.io/badge/Tailwind_CSS-4.3-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white
[java]: https://img.shields.io/badge/Java-21-ED8B00?style=flat-square&logo=openjdk&logoColor=white
[spring]: https://img.shields.io/badge/Spring_Boot-4.1-6DB33F?style=flat-square&logo=springboot&logoColor=white
[gradle]: https://img.shields.io/badge/Gradle-9.5-02303A?style=flat-square&logo=gradle&logoColor=white
[mybatis]: https://img.shields.io/badge/MyBatis-4.0-B21F24?style=flat-square
[postgresql]: https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white
[qdrant]: https://img.shields.io/badge/Qdrant-Vector_DB-DC244C?style=flat-square&logo=qdrant&logoColor=white
[python]: https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white
[pytorch]: https://img.shields.io/badge/PyTorch-2.5-EE4C2C?style=flat-square&logo=pytorch&logoColor=white
[yolo]: https://img.shields.io/badge/YOLO-v8-111F68?style=flat-square&logo=yolo&logoColor=white
[opencv]: https://img.shields.io/badge/OpenCV-4-5C3EE8?style=flat-square&logo=opencv&logoColor=white
[onnx]: https://img.shields.io/badge/ONNX-Runtime-005CED?style=flat-square&logo=onnx&logoColor=white
[gemini]: https://img.shields.io/badge/Gemini-2.5_Flash-8E75B2?style=flat-square&logo=googlegemini&logoColor=white
[elevenlabs]: https://img.shields.io/badge/ElevenLabs-TTS-000000?style=flat-square
[cplusplus]: https://img.shields.io/badge/C%2B%2B-17-00599C?style=flat-square&logo=cplusplus&logoColor=white
[cmake]: https://img.shields.io/badge/CMake-3-064F8C?style=flat-square&logo=cmake&logoColor=white
[arduino]: https://img.shields.io/badge/Arduino-Firmware-00878F?style=flat-square&logo=arduino&logoColor=white
[raspberrypi]: https://img.shields.io/badge/Raspberry_Pi-Controller-A22846?style=flat-square&logo=raspberrypi&logoColor=white
[mqtt]: https://img.shields.io/badge/MQTT-Protocol-660066?style=flat-square&logo=mqtt&logoColor=white
[mosquitto]: https://img.shields.io/badge/Eclipse_Mosquitto-Broker-3C5280?style=flat-square&logo=eclipsemosquitto&logoColor=white
[docker]: https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white
[nginx]: https://img.shields.io/badge/Nginx-Reverse_Proxy-009639?style=flat-square&logo=nginx&logoColor=white
[jenkins]: https://img.shields.io/badge/Jenkins-CI%2FCD-D24939?style=flat-square&logo=jenkins&logoColor=white
[bambulab]: https://img.shields.io/badge/Bambu_Lab-3D_Printer-00AE42?style=flat-square&logo=bambulab&logoColor=white
[printing3d]: https://img.shields.io/badge/FDM-3D_Printing-F28C28?style=flat-square
[cad3d]: https://img.shields.io/badge/3D_CAD-Design-4B72B8?style=flat-square
