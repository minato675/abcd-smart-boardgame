/**
 * 사물함 컨트롤러와 직접 주고받는 MQTT (관리자 강제 오픈용).
 *
 * inte-server 에는 사물함을 여는 REST 엔드포인트가 없다 — 발행은 전부
 * `RentService.openCabinetByCard`(카드 태그) 안에서만 일어난다. 그래서 관리자
 * 화면은 서버를 거치지 않고 브로커에 직접 붙어 컨트롤러 프로토콜을 그대로 쓴다
 * (손님 화면의 src/mqtt/roomMqtt.ts 와 같은 방식, 토픽만 다르다).
 *
 * ⚠️ **컨트롤러가 무시할 수 있다.** cabinet/controller/docs/protocol.md 기준으로
 * 컨트롤러는 `WAITING_SERVER` 상태에서 들어온 open 만 실행한다. 즉 카드 태그로
 * 트랜잭션이 열려 있지 않으면 이 명령은 조용히 버려지고, status 응답도 오지 않는다.
 * 화면이 응답을 기다렸다가 '컨트롤러가 응답하지 않음' 으로 끝내는 이유다 —
 * 보낸 즉시 '열렸다' 고 표시하면 거짓말이 된다.
 *
 * 서버를 거치지 않으므로 이 경로로 연 개폐는 cabinet_history 에도 남지 않는다.
 */

import mqtt, { type MqttClient } from 'mqtt'
import {
  CABINET_CONTROLLER_ID,
  MQTT_PASSWORD,
  MQTT_URL,
  MQTT_USERNAME,
} from '@/config/env'

/** 컨트롤러가 open 을 받아 문을 열기까지 기다려 주는 시간 */
export const OPEN_TIMEOUT_MS = 8000

/** `/cabinet/{controllerId}/{n}/status` 페이로드 */
export interface CabinetStatusMessage {
  cabinetId: number
  transactionId: string | null
  /** 'open' | 'closed' | 'error' */
  status: string
  /** status='error' 일 때 컨트롤러가 주는 분류 */
  detail?: string
  /** 그보다 자세한 아두이노 쪽 사유 */
  reason?: string
}

export type CabinetStatusHandler = (message: CabinetStatusMessage) => void

const STATUS_PATTERN = new RegExp(
  `^/cabinet/${escapeRegExp(CABINET_CONTROLLER_ID)}/(\\d+)/status$`,
)

const handlers = new Set<CabinetStatusHandler>()
const decoder = new TextDecoder()

let client: MqttClient | null = null
/** 한 세션 안에서 transactionId 가 겹치지 않게 하는 카운터 */
let sequence = 0

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** 브로커 주소가 설정돼 있는지. 없으면 강제 오픈 버튼을 비활성화한다. */
export function isCabinetMqttConfigured(): boolean {
  return MQTT_URL !== ''
}

export function isCabinetMqttConnected(): boolean {
  return client?.connected ?? false
}

/** 상태 보고 구독. 해제 함수를 돌려준다. */
export function onCabinetStatus(handler: CabinetStatusHandler): () => void {
  handlers.add(handler)
  return () => {
    handlers.delete(handler)
  }
}

function dispatch(topic: string, raw: Uint8Array): void {
  const match = STATUS_PATTERN.exec(topic)
  if (!match) return

  let payload: Record<string, unknown> = {}
  try {
    const text = decoder.decode(raw)
    if (text) payload = JSON.parse(text) as Record<string, unknown>
  } catch {
    // 컨트롤러가 평문을 보내는 경우가 있어 상태 없는 보고로 흘린다
  }

  const message: CabinetStatusMessage = {
    cabinetId: Number(match[1]),
    transactionId:
      typeof payload.transactionId === 'string' ? payload.transactionId : null,
    status: typeof payload.status === 'string' ? payload.status : 'unknown',
    detail: typeof payload.detail === 'string' ? payload.detail : undefined,
    reason: typeof payload.reason === 'string' ? payload.reason : undefined,
  }

  for (const handler of handlers) {
    try {
      handler(message)
    } catch (error) {
      // 핸들러 하나가 던져도 나머지 구독은 살아 있어야 한다
      console.error('[cabinet-mqtt] 핸들러 실패', error)
    }
  }
}

/**
 * 브로커 연결 + 이 컨트롤러의 상태 토픽 구독.
 *
 * 손님 화면의 roomMqtt 와 클라이언트를 나눠 쓴다 — 구독 필터가 다르고
 * (`/cabinet/...` vs `/room/...`), 관리자 화면을 열지 않으면 연결할 이유도 없다.
 */
export function connectCabinetMqtt(): void {
  if (client || !MQTT_URL) return

  const filter = `/cabinet/${CABINET_CONTROLLER_ID}/+/status`

  client = mqtt.connect(MQTT_URL, {
    clientId: `admin-${Math.random().toString(16).slice(2, 10)}`,
    username: MQTT_USERNAME || undefined,
    password: MQTT_PASSWORD || undefined,
    clean: true,
    reconnectPeriod: 3000,
    connectTimeout: 10000,
  })

  client.on('connect', () => {
    client?.subscribe(filter, { qos: 1 }, (error) => {
      if (error) {
        console.error(`[cabinet-mqtt] 구독 실패 - ${filter}`, error)
        return
      }
      console.info(`[cabinet-mqtt] 구독 - ${filter}`)
    })
  })

  client.on('message', (topic, payload) => dispatch(topic, payload))
  client.on('error', (error) => console.error('[cabinet-mqtt] 연결 오류', error))
}

/** 프로토콜 문서의 예시(`rpi-01-20260729-120000-000001`)와 같은 모양으로 만든다 */
function nextTransactionId(): string {
  const now = new Date()
  const pad = (value: number, length = 2) => String(value).padStart(length, '0')
  const date = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`
  const time = `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  sequence += 1
  return `${CABINET_CONTROLLER_ID}-${date}-${time}-a${pad(sequence, 5)}`
}

/**
 * 강제 오픈 명령 발행. 실제로 열렸는지는 status 보고로만 알 수 있으므로
 * 여기서는 발행에 쓴 transactionId 만 돌려준다.
 *
 * @param mode 'receive' = 꺼내기, 'return' = 넣기. 컨트롤러가 아두이노에
 *             `COMMAND:RECEIVE` / `COMMAND:RETURN` 으로 번역해 보낸다.
 */
export function publishCabinetOpen(
  cabinetId: number,
  mode: 'receive' | 'return',
): string {
  if (!client) connectCabinetMqtt()

  const transactionId = nextTransactionId()
  const topic = `/cabinet/${CABINET_CONTROLLER_ID}/${cabinetId}/open`
  const payload = JSON.stringify({ transactionId, step: 1, mode })

  // retain=true 로 보내면 컨트롤러가 거부한다(프로토콜 문서 참고)
  client?.publish(topic, payload, { qos: 1, retain: false }, (error) => {
    if (error) console.error(`[cabinet-mqtt] 발행 실패 - ${topic}`, error)
  })

  return transactionId
}

/** 개발 중 HMR 로 모듈이 갈릴 때 연결이 쌓이는 것을 막는다 */
if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    client?.end(true)
    client = null
  })
}
