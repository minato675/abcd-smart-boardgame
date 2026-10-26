/**
 * 배포 환경별 설정값을 읽는 유일한 지점.
 *
 * 값은 .env.local 로 주입한다(.env.example 참고). 태블릿마다 달라지는 것은
 * ROOM_NUMBER 하나뿐이므로, 기기 프로비저닝이 도입되면 이 파일만 바꾸면 된다.
 */

/**
 * API 접두어. inte-server 에 CORS 설정이 없어 same-origin 이어야 하므로
 * 절대 URL 이 아니라 경로 접두어를 쓴다. 운영에서는 외부 nginx 가,
 * 개발에서는 vite server.proxy 가 이 접두어를 inte-server:8111 로 넘긴다.
 */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/inte'

/**
 * 이 태블릿이 설치된 방 번호.
 *
 * inte-server 에는 인증이 없고 이 값이 곧 신원이다 — /rent, /reservation 의
 * 요청 본문에 그대로 실린다. DB room 테이블의 room_number 와 문자열이 정확히
 * 같아야 하며, 다르면 모든 쓰기 요청이 404 ROOM_NOT_FOUND 로 실패한다.
 */
export const ROOM_NUMBER: string = import.meta.env.VITE_ROOM_NUMBER ?? 'room-01'

/** 헤더에 표시할 방 이름 (표시용, 서버로 나가지 않는다) */
export const ROOM_LABEL: string =
  import.meta.env.VITE_ROOM_LABEL ?? `Room ${ROOM_NUMBER}`

/** 헤더에 표시할 카페 이름 (표시용) */
export const CAFE_NAME: string = import.meta.env.VITE_CAFE_NAME ?? 'ABCd'

/**
 * MQTT 브로커의 WebSocket 주소 (예: ws://i15a402.p.ssafy.io:9001).
 *
 * REST 와 달리 브로커에 **직접** 붙는다 — API_BASE_URL 프록시를 타지 않는다.
 * WebSocket 은 CORS 대상이 아니라 교차 오리진이어도 막히지 않지만, 페이지가
 * https 로 서비스되면 ws:// 는 mixed content 로 차단되므로 wss:// 여야 한다.
 *
 * 비워 두면 구독을 시도하지 않는다(브로커 없이 도는 개발 환경).
 */
export const MQTT_URL: string = import.meta.env.VITE_MQTT_URL ?? ''

/** 브로커에 인증이 걸려 있을 때만 채운다 */
export const MQTT_USERNAME: string = import.meta.env.VITE_MQTT_USERNAME ?? ''
export const MQTT_PASSWORD: string = import.meta.env.VITE_MQTT_PASSWORD ?? ''

/**
 * 사물함 컨트롤러(라즈베리파이) 식별자. 관리자 화면의 강제 오픈이
 * `/cabinet/{controllerId}/{cabinetNumber}/open` 으로 발행할 때 쓴다.
 *
 * 서버 쪽 값은 DB `room_rfid.controller_id` 이고, 컨트롤러 쪽 값은
 * cabinet/controller/config/controller.conf 의 controller_id 다. 둘이 같아야 한다.
 */
export const CABINET_CONTROLLER_ID: string =
  import.meta.env.VITE_CABINET_CONTROLLER_ID ?? 'rpi-01'

/**
 * ElevenLabs 음성. AI 심판 규칙 위반 메시지를 읽는 목소리를 고른다.
 *
 * 기본값은 ElevenLabs 기본 라이브러리의 'George' 보이스.
 */
export const ELEVENLABS_VOICE_ID: string =
  import.meta.env.VITE_ELEVENLABS_VOICE_ID ?? 'JBFqnCBsd6RMkjVDRZzb'

/**
 * ElevenLabs API 키.
 *
 * 주의: VITE_ 로 시작하는 값은 전부 빌드 결과물(JS 번들)에 그대로 박혀 브라우저에서
 * 누구나 볼 수 있다. 지금은 프런트에서 바로 호출하는 임시 구조이고, 운영에서는
 * 이 호출을 백엔드로 옮겨 키를 감춰야 한다.
 */
export const ELEVENLABS_API_KEY: string = import.meta.env.VITE_ELEVENLABS_API_KEY ?? ''

/**
 * 관리자 화면이 관리하는 방 번호 목록 (쉼표 구분).
 *
 * 서버에 방 목록 조회 API 가 없어서(GET /room 이 없다) 설정으로 받는다.
 * 여기 적힌 번호는 DB `room.room_number` 와 정확히 같아야 입/퇴실이 통한다.
 */
export const ADMIN_ROOM_NUMBERS: string[] = (
  import.meta.env.VITE_ADMIN_ROOM_NUMBERS ?? '1,2,3,4,5,6'
)
  .split(',')
  .map((value) => value.trim())
  .filter(Boolean)

if (!import.meta.env.DEV && !import.meta.env.VITE_ROOM_NUMBER) {
  console.warn(
    `[config] VITE_ROOM_NUMBER 가 설정되지 않아 기본값 '${ROOM_NUMBER}' 을 사용합니다. ` +
      '실제 방 번호와 다르면 대여/예약이 모두 실패합니다.',
  )
}
