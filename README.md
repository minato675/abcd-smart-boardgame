# ABCd — 스마트 보드게임 카페

태블릿, AI와 RFID 스마트 보관함을 연결해 보드게임 검색·대여·반납과 플레이 보조를 제공하는 팀 프로젝트입니다.

| 항목 | 내용 |
| --- | --- |
| 프로젝트 | SSAFY 공통 프로젝트 · S15P11A402 |
| 기간 | 2026.07–2026.08 |
| 개인 담당 | 사물함 회로 설계·구현, 카메라 지지대 3D 프린팅 |
| 저장소 용도 | 팀 프로젝트의 코드와 개인 담당 근거를 정리한 비공개 포트폴리오 |

## 개인 기여

김지호는 RFID 태그, 문 센서, 전자 잠금장치와 LED가 연동되는 사물함 회로를 설계·구현하고,
카메라 지지대를 3D 프린팅했습니다. 임베디드 개발을 처음 접하면서 GPT로 개념을 확인하고,
부품 동작을 학습하며 회로를 구성·점검했습니다.

원본 README의 팀 역할 표와 회고를 근거로 담당 범위를 정리했습니다.
보관함 Raspberry Pi 컨트롤러·RFID SDK·음성 호출어는 박건우, 루미큐브 MC는 김형수,
음성 QnA는 임다빈의 담당 기록이 있습니다. 이 저장소에 포함된 팀 코드 전체를 개인 단독 구현으로 설명하지 않습니다.

## 팀이 구현한 흐름

1. 태블릿에서 보드게임을 검색하고 대여·예약합니다.
2. 통합 서버가 대여·재고 상태와 보관함 제어를 연결합니다.
3. RFID와 Bluetooth 통신으로 보관함을 열고, 문 센서로 대여·반납 흐름을 확인합니다.
4. 게임 중 음성 규칙 QnA와 카메라 기반 루미큐브 판정 보조를 제공합니다.

```text
태블릿(Vue) ─ REST ─ 통합 서버(Spring Boot) ─ PostgreSQL
                    │ MQTT
                    ├─ Raspberry Pi ─ Bluetooth ─ Arduino 보관함
                    └─ Jetson: 음성 QnA · 호출어 · 루미큐브 분석
```

## 살펴볼 코드

| 경로 | 내용 |
| --- | --- |
| [cabinet/unit](cabinet/unit/README.md) | 잠금장치·문 센서·LED와 Bluetooth 명령을 처리하는 Arduino 펌웨어 |
| [cabinet/controller](cabinet/controller/README.md) | Raspberry Pi 컨트롤러, RFID SDK, MQTT·모의 장치 테스트 |
| [boardgame-frontend](boardgame-frontend/README.md) | 손님용 태블릿과 관리자 화면 |
| [inte-server](inte-server/) | REST API, DB와 MQTT 통합 서버 |
| [table](table/) | 루미큐브 분석·음성 QnA·호출어 감지 |

회로 배선과 동작 순서는 [보관함 유닛 안내](cabinet/unit/README.md)에서 확인할 수 있습니다.
3D CAD 원본과 프린팅 결과 사진은 이번 GitLab 소스 ZIP에서 확인되지 않아 별도 산출물로 추가하지 않았습니다.

## 실행과 검증 범위

- 웹: `boardgame-frontend`에서 `npm install`, `npm run dev`.
- 통합 서버: `inte-server`에서 Gradle Wrapper로 실행합니다. DB·MQTT 환경 설정이 필요합니다.
- 보관함: Arduino·Raspberry Pi와 부품 연결이 필요하며, 설치·테스트 명령은 각 폴더 README를 따릅니다.
- 모델 가중치와 설치용 wheel은 게시 범위에서 제외했습니다. AI 기능 실행에는 해당 외부 파일이 필요합니다.
- 이번 정리는 소스 선별과 게시 검증입니다. 하드웨어 연결·인식 정확도·전체 서비스 동작을 새로 검증한 결과는 아닙니다.

[게시 범위와 원본 기준](docs/EXPORT_SCOPE.md) · [포트폴리오 설명](docs/PORTFOLIO.md) · [원본 팀 README](docs/source/README.original.md)
