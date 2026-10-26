import mqtt, { type MqttClient } from 'mqtt'
import { MQTT_PASSWORD, MQTT_URL, MQTT_USERNAME, ROOM_NUMBER } from '@/config/env'

/**
 * 이 방의 MQTT 이벤트를 브로커에서 **직접** 구독한다.
 *
 * inte-server 를 거치지 않는다. 서버가 이미 브로커로 주고받는 메시지를 태블릿이
 * 그대로 듣는 구조라, 새 이벤트 토픽이 생겨도 서버에 중계 코드를 추가할 필요가 없다.
 * 참고: inte-server/src/main/java/com/ssafy/boardgame/mqtt/MqttSubTopics.java
 *
 * 토픽은 `/room/{roomNumber}/...` 형태이고, 핸들러는 방 접두어를 뗀 나머지
 * (예: 'qna/ready')로 등록한다.
 *
 * 주의: 발행 시점에 태블릿이 연결돼 있지 않으면 그 메시지는 못 받는다. 새로고침이나
 * Wi-Fi 끊김 뒤에도 상태를 복원하려면 발행 쪽에서 retain 을 켜거나(브로커가 구독
 * 시점에 마지막 값을 재생한다) REST 로 현재 상태를 다시 읽어야 한다.
 */

/** 방 접두어를 뗀 토픽. 예: '/room/1/qna/ready' -> 'qna/ready' */
export type RoomTopic = string

/**
 * @param payload JSON 이면 파싱된 객체, 아니면 원본 문자열
 * @param topic   방 접두어를 뗀 토픽
 */
export type RoomEventHandler = (payload: unknown, topic: RoomTopic) => void

const ROOM_PREFIX = `/room/${ROOM_NUMBER}/`
const ROOM_FILTER = `/room/${ROOM_NUMBER}/#`

/**
 * 보드게임 재고 방송. 방 접두어가 없는 유일한 토픽이다 - 대여/반납은 이 방이 한 일이든
 * 남의 방이 한 일이든 모든 태블릿의 목록 화면에 영향을 준다.
 * 참고: inte-server MqttPubTopics.boardGameEvent()
 */
const BOARD_GAME_EVENT_TOPIC = '/boardgame/event'

export type BoardGameEventHandler = (payload: unknown) => void
const boardGameEventHandlers = new Set<BoardGameEventHandler>()

/** 보드게임 재고 방송 구독. 해제 함수를 돌려준다. */
export function onBoardGameEvent(handler: BoardGameEventHandler): () => void {
  boardGameEventHandlers.add(handler)
  return () => boardGameEventHandlers.delete(handler)
}

const handlers = new Map<RoomTopic, Set<RoomEventHandler>>()
const decoder = new TextDecoder()

let client: MqttClient | null = null

/** 브로커가 연결돼 있는지 (연결 표시가 필요한 화면용) */
export function isRoomMqttConnected(): boolean {
  return client?.connected ?? false
}

/**
 * 방 이벤트 구독 등록. 해제 함수를 돌려준다.
 *
 * 연결 전에 불러도 된다 — 핸들러 등록과 연결은 무관하다.
 */
export function onRoomEvent(
  topic: RoomTopic,
  handler: RoomEventHandler,
): () => void {
  const existing = handlers.get(topic) ?? new Set<RoomEventHandler>()
  existing.add(handler)
  handlers.set(topic, existing)

  return () => {
    const set = handlers.get(topic)
    if (!set) return
    set.delete(handler)
    if (set.size === 0) handlers.delete(topic)
  }
}

function toPayload(raw: Uint8Array): unknown {
  const text = decoder.decode(raw)
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    // 빈 JSON 이 아닌 평문을 보내는 발행자도 있어서 문자열 그대로 넘긴다
    return text
  }
}

function dispatch(fullTopic: string, raw: Uint8Array): void {
  if (fullTopic === BOARD_GAME_EVENT_TOPIC) {
    const payload = toPayload(raw)
    for (const handler of boardGameEventHandlers) {
      try {
        handler(payload)
      } catch (error) {
        console.error('[mqtt] 핸들러 실패 - topic=/boardgame/event', error)
      }
    }
    return
  }

  if (!fullTopic.startsWith(ROOM_PREFIX)) return

  const topic = fullTopic.slice(ROOM_PREFIX.length)
  const set = handlers.get(topic)
  if (!set || set.size === 0) return

  const payload = toPayload(raw)
  for (const handler of set) {
    try {
      handler(payload, topic)
    } catch (error) {
      // 핸들러 하나가 던져도 나머지 핸들러와 이후 수신은 살아 있어야 한다
      console.error(`[mqtt] 핸들러 실패 - topic=${topic}`, error)
    }
  }
}

/**
 * 브로커 연결 + 이 방 토픽 구독. 앱 시작 시 한 번만 부르면 된다(중복 호출은 무시).
 *
 * 재연결은 mqtt.js 가 알아서 하고, 구독은 'connect' 마다 다시 걸어서
 * 재연결 후에도 이벤트가 계속 들어오게 한다.
 */
export function connectRoomMqtt(): void {
  if (client) return

  if (!MQTT_URL) {
    console.warn(
      '[mqtt] VITE_MQTT_URL 이 없어 방 이벤트를 구독하지 않습니다. ' +
        '음성 도우미가 준비 완료(qna/ready)를 받지 못해 대기 화면에서 멈춥니다.',
    )
    return
  }

  client = mqtt.connect(MQTT_URL, {
    // 브로커는 clientId 가 겹치면 앞의 연결을 끊는다. 같은 방을 여러 창에서 열어도
    // 서로를 밀어내지 않도록 난수를 섞는다.
    clientId: `tablet-${ROOM_NUMBER}-${Math.random().toString(16).slice(2, 10)}`,
    username: MQTT_USERNAME || undefined,
    password: MQTT_PASSWORD || undefined,
    // 태블릿은 놓친 메시지를 몰아서 받아도 쓸모가 없다(지난 상태를 뒤늦게 그린다).
    clean: true,
    reconnectPeriod: 3000,
    connectTimeout: 10000,
  })

  client.on('connect', () => {
    client?.subscribe(ROOM_FILTER, { qos: 1 }, (error) => {
      if (error) {
        console.error(`[mqtt] 구독 실패 - ${ROOM_FILTER}`, error)
        return
      }
      console.info(`[mqtt] 구독 - ${ROOM_FILTER}`)
    })
    client?.subscribe(BOARD_GAME_EVENT_TOPIC, { qos: 1 }, (error) => {
      if (error) {
        console.error(`[mqtt] 구독 실패 - ${BOARD_GAME_EVENT_TOPIC}`, error)
        return
      }
      console.info(`[mqtt] 구독 - ${BOARD_GAME_EVENT_TOPIC}`)
    })
  })

  client.on('message', (topic, payload) => dispatch(topic, payload))

  client.on('error', (error) => {
    // 인증 실패나 브로커 다운. mqtt.js 가 reconnectPeriod 마다 다시 시도한다.
    console.error('[mqtt] 연결 오류', error)
  })
}

/** 개발 중 HMR 로 모듈이 갈릴 때 연결이 쌓이는 것을 막는다 */
if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    client?.end(true)
    client = null
  })
}
