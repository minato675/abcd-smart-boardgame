# boardgame-frontend

보드게임 카페 태블릿 화면 (Vue 3 + TypeScript + Vite + Tailwind v4).
백엔드는 같은 저장소의 `inte-server` (Spring Boot, 포트 8111).

## 실행

```bash
cp .env.example .env.local   # 값 확인 후 수정 (특히 VITE_ROOM_NUMBER)
npm install
npm run dev
```

`.env.local` 없이도 코드 기본값(`/inte`, `http://localhost:8111`, 방 `1`)으로 동작한다.

백엔드도 같이 띄워야 한다:

```bash
cd ../inte-server && ./gradlew bootRun
```

### 방 입실 처리가 먼저 필요하다

방 상태가 `EMPTY` 면 대여/예약 요청이 전부 `409 ROOM_NOT_IN_USE` 로 막힌다.
관리자 화면 [`/admin/rooms`](#관리자-화면-admin) 에서 그 방을 **입실 처리** 하거나,
개발 화면 좌측 하단의 **`[dev] 입실 처리`** 버튼을 한 번 누르거나(dev 빌드에서만 보인다):

```bash
curl -X POST http://localhost:8111/admin/room/update \
  -H 'Content-Type: application/json' -d '{"roomNumber":"1","status":"USE"}'
```

`404 ROOM_NOT_FOUND` 가 나오면 `VITE_ROOM_NUMBER` 가 DB `room.room_number` 와 다르다는 뜻이다.

## API 연동 구조

| 계층 | 파일 | 역할 |
|---|---|---|
| 설정 | `src/config/env.ts` | `VITE_*` 를 읽는 유일한 지점 (base URL, 방 번호) |
| 전송 | `src/api/http.ts` | fetch 래퍼, `ApiError{status, code, message}` |
| 서버 원본 | `src/api/dto.ts` | inte-server Java DTO 와 1:1 |
| 변환 | `src/api/mappers.ts` | DTO → 도메인 (`boardGameId`→`id` 등) |
| 호출 | `src/api/games.ts`, `src/api/admin.ts` | 엔드포인트별 함수, `roomNumber` 주입 |
| 도메인 | `src/types/game.ts` | 화면이 쓰는 타입과 표시용 헬퍼 |

화면/컴포저블은 DTO 를 직접 보지 않는다. 서버가 필드명을 바꾸면 `dto.ts` 와
`mappers.ts` 두 곳만 고치면 된다.

인증은 없고 **요청 본문의 `roomNumber` 가 곧 신원**이다. 그 값은 `games.ts` 가
직접 주입하므로 화면 코드는 방 번호를 몰라도 된다.

### 사용하는 엔드포인트

| 기능 | 호출 |
|---|---|
| 목록 / 이름 검색 | `GET /boardgame?keyword=` |
| 상세 | `GET /boardgame/{boardGameId}` |
| 대여 | `POST /rent` `{boardGameId, roomNumber}` → `cabinetId` 반환 |
| 대여 상태 복원 | `GET /rent?roomNumber=` → 미반납 대여 + `status` |
| 예약 | `POST /reservation` `{boardGameId, roomNumber}` |
| 예약 취소 | `PATCH /reservation/cancel` `{roomNumber, reservationId}` |
| 예약 복원 | `GET /reservation?roomNumber=&status=WAITING` |
| 입실(dev) | `POST /admin/room/update` `{roomNumber, status}` |
| 입실(관리자) | `POST /admin/room/checkin` `{roomNumber}` → 이용 이력까지 생성 |
| 퇴실(관리자) | `POST /admin/room/checkout` `{roomNumber}` → 대여·예약 정리까지 |

필터링은 전부 클라이언트에서 한다. 검색어를 지울 때 재요청이 없어 태블릿에서
즉각적이고, 상황별 칩('처음이에요' / '30분 안에' / '지금 가능')은 서버 파라미터가 없다.

### 게임 하나의 상태를 어떻게 정하나

`availableCount > 0` 만으로는 **내가 빌려서 재고가 없는 것**과 **다른 팀이 빌려서 없는
것**이 구분되지 않는다. 서버는 두 경우 모두 `ALREADY_RENTED` 로 거절하므로, 화면이
그걸 미리 알아야 예약 버튼을 잘못 띄우지 않는다. `resolveGameState`(`src/types/game.ts`)
가 **우리 방 상태를 재고보다 먼저** 보고 다섯 상태 중 하나를 정한다:

| 상태 | 판정 | 버튼 |
|---|---|---|
| `using` | `rent.status = USING` | 반납 방법 (안내) |
| `pickup` | `rent.status = RENT` | 꺼내는 방법 (안내) |
| `reserved` | `reservation.status = WAITING` | 비활성 |
| `available` | `availableCount > 0` | 대여하기 |
| `rentedOut` | 나머지 | 빌리기 예약 |

`rent.status` 는 **카드 태그 → MQTT → 서버**(`CabinetService.advanceRent`)에서만
전이된다. 태블릿은 통보받을 방법이 없어, 화면 진입·대여·예약·반납 알림 등 상태가
바뀔 만한 시점마다 `useRoomRents` 가 다시 묻는다.

**대여 버튼은 사물함을 열지 않는다.** MQTT 발행은 `RentService.openCabinetByCard`
에서만 일어난다 — `POST /rent` 의 `cabinetId` 는 '태그하면 열릴 사물함'이다.
그리고 `findActiveRent` 가 `USING` 을 먼저 집으므로, 쓰는 중에 다음 게임을 대여하면
**태그 1회 = 현재 게임 반납, 2회 = 새 게임 픽업** 이다(`CabinetGuideModal` 이 안내한다).

### CORS 와 `/inte` 접두어

`inte-server` 에는 CORS 설정이 **전혀 없다.** 그래서 프론트는 항상 same-origin 으로
호출하고, 경로 접두어 `/inte` 를 백엔드로 넘기는 책임을 프록시에 맡긴다.

- 개발: `vite.config.ts` 의 `server.proxy` 가 `/inte` → `VITE_DEV_API_TARGET` 로 넘기고 접두어를 벗긴다.
- 운영: 외부 nginx 가 같은 일을 해야 한다. `inte-server` 에 `context-path` 가
  없으므로 `proxy_pass` 끝의 슬래시가 접두어를 벗기는 핵심이다.

  ```nginx
  location /inte/ { proxy_pass http://inte-server:8111/; }
  ```

`VITE_API_BASE_URL` 에 절대 URL(`http://...`)을 넣으면 브라우저가 CORS 로 막는다.

> 참고: 이 저장소에는 nginx 설정이 없다(배포 서버 `/home/ubuntu`). SPA 라우팅용
> `try_files $uri /index.html` 도 확인이 필요하다 — 없으면 `/games/3` 에서
> 새로고침할 때 404 가 난다.

## 관리자 화면 (`/admin`)

카운터 PC 용 화면이다. 손님 태블릿과 같은 앱·같은 디자인 토큰을 쓰지만
`TabletFrame`(1024x600) 밖에 있고, 코드는 `src/admin/` 아래에 모여 있다.
라우트는 지연 로딩이라 태블릿 번들에 차트/표 코드가 섞이지 않는다.

**데모라 로그인이 없다.** 주소를 아는 사람은 누구나 들어온다. 실서비스로 가려면
라우트 가드와 서버 인증이 함께 필요하다.

| 경로 | 화면 | 하는 일 |
|---|---|---|
| `/admin` | 통계 대시보드 | KPI 12종 + 차트 7종 + 게임별 상세표. 기간 필터(오늘/7일/30일) |
| `/admin/rooms` | 방 현황 | 방별 실시간 상태, **입실 · 퇴실 처리** |
| `/admin/rents` | 대여 현황 | 미반납 대여, 미수령/장시간 감지, 강제 반납 |
| `/admin/cabinets` | 재고 · 사물함 | 게임별 재고, 사물함 칸별 상태, **강제 오픈** |
| `/admin/ai` | AI 사용 로그 | 규칙 질문 · 턴 판정 · 반칙 감지 타임라인 |

### 무엇이 진짜고 무엇이 데모 데이터인가

이 구분이 이 화면에서 제일 중요하다.

| 기능 | 서버 반영 | 근거 |
|---|---|---|
| 입실 | ✅ | `POST /admin/room/checkin` |
| 퇴실 | ✅ | `POST /admin/room/checkout` (서버가 대여 반납·예약 취소까지 정리) |
| 사물함 강제 오픈 | ⚠️ 브로커 직접 | REST 없음. MQTT `/cabinet/{id}/{n}/open` 으로 직접 발행 |
| 통계 · 방 목록 · 사물함 · 강제 반납 | ❌ 화면만 | 대응 엔드포인트 없음 |

서버 호출이 실패해도 화면 상태는 바뀌지만, 토스트가 **서버 반영 실패**를 그대로
알린다(`src/admin/store.ts` 의 `ActionResult`). 백엔드를 안 띄워도 화면은 돌아간다.

**통계는 요약값을 지어내지 않는다.** `src/admin/demoData.ts` 가 만드는 건 원자료
(이용 이력·대여·예약 행)뿐이고, 모든 수치는 `src/admin/stats.ts` 가 그걸 실제로
집계해서 낸다. 그래서 방 현황에서 퇴실을 누르면 대시보드의 '현재 이용 중' 과
'평균 체류 시간' 이 실제로 따라 움직인다. 서버에 `GET /admin/stats` 가 생기면
`StatsBundle` 을 그대로 응답 계약으로 쓰고 `demoData.ts` 만 지우면 된다.

씨앗은 오늘 날짜라 하루 동안은 새로고침해도 같은 데이터가 나온다.

### 강제 오픈이 무시될 수 있다

`cabinet/controller/docs/protocol.md` 기준으로 컨트롤러는 **`WAITING_SERVER`
상태에서 들어온 open 만** 실행한다. 카드 태그로 시작된 거래가 없으면 명령은
조용히 버려지고 status 보고도 오지 않는다. 그래서 화면은 발행 즉시 '열렸다' 고
하지 않고 컨트롤러의 status 를 8초간 기다렸다가, 응답이 없으면 실패로 표시한다.

서버를 거치지 않으므로 이 경로의 개폐는 `cabinet_history` 에 남지 않는다.

### 차트 규칙

`src/admin/charts/palette.ts` 에 정리돼 있다. 요약하면:

- 색 슬롯 8개는 **고정 순서**로만 배정한다(순서 자체가 색각 이상 안전성의 근거다).
  9번째 계열은 새 색을 만들지 않고 '기타'로 접는다.
- 순서가 있는 값(난이도, 퍼널 단계)만 한 색상 계열의 명도 단계를 쓴다.
  순서 없는 항목을 값 크기에 따라 진하게 칠하지 않는다 — 막대 길이가 이미 그 일을 한다.
- 축은 하나만 쓴다. 단위가 다른 값은 차트를 나눈다.
- 모든 차트에 **표 보기**가 있다. 라이트 모드에서 일부 슬롯은 흰 배경 대비가
  3:1 미만이라, 색만으로 값을 전달하면 안 되기 때문이다.
- 색은 전부 CSS 변수(`--color-viz-*`, `src/style.css`)라 다크 모드가 자동으로 따라온다.

## 아직 목업인 것

백엔드에 대응 기능이 없어서 남겨둔 부분:

- **반납 알림 플로우** (`useReservation` 의 `openAlert`/`acceptAlert`) — 브라우저
  푸시 채널(WS/SSE)도, 예약 수락 엔드포인트도 없다. dev 버튼으로만 확인 가능.
- **규칙 도우미** (`useRuleAssistant`) — STT 도, 질의 엔드포인트도 없어서 목업 답변
  3개가 순환한다. 검색 바의 '규칙 물어보기' 버튼이 이걸 연다.
- **헤더의 `사용 시간`** — `room` 테이블에 입실 시각 컬럼이 없어 실제로는
  태블릿 가동 시간을 센다.
## 알려진 백엔드 문제

**`GET /boardgame` 이 `name`/`difficulty`/`playTime`/`totalCount` 등을 모두
null·0 으로 반환한다.** `BoardGameMapper.xml` 의 두 resultMap 이 `boardGameId` 와
nested `<collection>`(categories) 만 선언하고 있는데, MyBatis 기본
`autoMappingBehavior=PARTIAL` 은 nested result mapping 을 가진 resultMap 의
자동 매핑을 끈다. 그래서 나머지 컬럼이 조용히 버려진다.

- 근거: `GET /reservation` 은 `boardGameName: "스플렌더"` 를 정상 반환한다
  (이쪽은 resultMap 없이 `resultType` 을 쓴다) → DB 에는 값이 있다.
- 해결: resultMap 에 `<result>` 를 명시하거나 `autoMapping="true"` 를 준다.
- 프론트는 그때까지 이름을 `이름 미등록`, 나머지를 `정보 없음` 으로 표시한다.

그 외: 개별 반납 엔드포인트 없음(재고가 퇴실 때만 복구됨), `WAITING`→`FULFILLED`
전이 누락(`fulfillByRoomAndGame` 이 작성돼 있으나 미호출), 카테고리 목록
엔드포인트 없음(필터 칩을 로드된 게임에서 역산), `keyword` 가 이름만 검색,
이미지 업로드/서빙 없음.

## 빌드

```bash
npm run build    # vue-tsc -b && vite build
```
