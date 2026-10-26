/**
 * 관리자 화면이 공유하는 상태 한 벌.
 *
 * 화면마다 따로 불러오면 방 현황에서 퇴실을 눌렀을 때 대시보드 수치가 그대로 남는다.
 * 다섯 화면이 같은 원자료를 보고 각자 집계하도록 모듈 단위 싱글턴으로 둔다.
 *
 * **서버와의 관계.** 전부 데모다 — 백엔드를 아예 치지 않는다. 입·퇴실을 포함해
 * 여기 있는 로컬 원자료만 고쳐서 화면에 보여 준다. `ActionResult` 는 이전에
 * 서버 호출이 있었을 때의 흔적으로, 항상 `synced: true` 를 돌려준다.
 */

import { computed, ref, shallowRef, watch } from 'vue'
import { ADMIN_ROOM_NUMBERS, ROOM_NUMBER } from '@/config/env'
import {
  connectCabinetMqtt,
  isCabinetMqttConfigured,
  onCabinetStatus,
  OPEN_TIMEOUT_MS,
  publishCabinetOpen,
} from './cabinetMqtt'
import { createDemoDataset, HOUR, startOfDay } from './demoData'
import type { DemoDataset } from './demoData'
import { buildStats, toAdminRents } from './stats'
import type {
  AdminRoom,
  AiLogRow,
  CabinetOpenAttempt,
  CabinetSlot,
  DoorState,
  StatsRange,
} from './types'

/** 방 정원. room.capacity 를 읽을 API 가 없어 번호 순으로 정해 둔다. */
const CAPACITY_BY_INDEX = [4, 4, 6, 6, 8, 8]

/** 화면에 실제로 그리는 AI 로그 상한. 턴 판정은 한 판에 수십 건씩 쌓인다. */
const AI_LOG_LIMIT = 400

/** 쓰기 동작의 결과. 데모 모드에서는 항상 synced: true 다. */
export interface ActionResult {
  synced: boolean
  error: string | null
}

/**
 * 발표가 문 열자마자(오전 9~11시)에 열려도 '오늘' 수치가 전부 0으로 보이지
 * 않도록, 오늘치 데이터는 최소 이 시각까지는 진행된 것으로 본다. 실제 지금
 * 시각이 이보다 늦으면 그대로 실제 시각을 쓴다 — 평소 시간대에 켜면 동작이
 * 실제 시계와 같다.
 */
const MIN_DEMO_HOUR = 14

function computeVirtualNow(real: number): number {
  return Math.max(real, startOfDay(real) + MIN_DEMO_HOUR * HOUR)
}

/** 실제 시계와 이 시계 사이의 간격. `now` 는 매초 이 간격만큼 앞선 채로 흐른다. */
const realStart = Date.now()
const virtualStart = computeVirtualNow(realStart)

const now = ref(virtualStart)
/** 통계용 시계. 초 단위로 다시 집계할 이유가 없어 따로 둔다. */
const statsClock = ref(virtualStart)

const dataset = shallowRef<DemoDataset>(
  createDemoDataset(ADMIN_ROOM_NUMBERS, virtualStart),
)

const range = ref<StatsRange>('today')

/** 컨트롤러가 보고한 문 상태. 보고가 없으면 닫힘으로 본다. */
const doorStates = ref(new Map<number, DoorState>())

/** 진행 중이거나 방금 끝난 강제 오픈 시도. 사물함 카드가 이걸 그린다. */
const openAttempts = ref(new Map<number, CabinetOpenAttempt>())

let clocksStarted = false

/** 화면이 열릴 때 한 번만: 시계 시작 + 사물함 상태 구독 */
function start(): void {
  if (clocksStarted) return
  clocksStarted = true

  setInterval(() => {
    now.value = virtualStart + (Date.now() - realStart)
  }, 1000)
  setInterval(() => {
    statsClock.value = virtualStart + (Date.now() - realStart)
  }, 60_000)

  if (!isCabinetMqttConfigured()) return
  connectCabinetMqtt()
  onCabinetStatus((message) => {
    const next = new Map(doorStates.value)
    next.set(
      message.cabinetId,
      message.status === 'open'
        ? 'OPEN'
        : message.status === 'error'
          ? 'FAULT'
          : 'CLOSED',
    )
    doorStates.value = next

    const attempt = openAttempts.value.get(message.cabinetId)
    if (!attempt || attempt.phase === 'opened' || attempt.phase === 'failed') return

    resolveAttempt(message.cabinetId, {
      ...attempt,
      phase: message.status === 'error' ? 'failed' : 'opened',
      reason:
        message.status === 'error'
          ? (message.reason ?? message.detail ?? '컨트롤러가 오류를 보고했습니다.')
          : null,
    })
  })
}

function resolveAttempt(cabinetId: number, attempt: CabinetOpenAttempt): void {
  const next = new Map(openAttempts.value)
  next.set(cabinetId, attempt)
  openAttempts.value = next
}

/* ── 파생 상태 ─────────────────────────────────────────── */

const rooms = computed<AdminRoom[]>(() =>
  ADMIN_ROOM_NUMBERS.map((roomNumber, index) => {
    const roomSessions = dataset.value.sessions.filter(
      (session) => session.roomNumber === roomNumber,
    )
    const open = roomSessions.find((session) => session.endedAt === null) ?? null
    const lastEndedAt = roomSessions.reduce<number | null>(
      (latest, session) =>
        session.endedAt !== null && (latest === null || session.endedAt > latest)
          ? session.endedAt
          : latest,
      null,
    )

    return {
      roomNumber,
      label: `${roomNumber}번 방`,
      capacity: CAPACITY_BY_INDEX[index] ?? 6,
      status: open ? 'USE' : 'EMPTY',
      startedAt: open?.startedAt ?? null,
      lastEndedAt,
      partySize: open?.partySize ?? null,
      isLocal: roomNumber === ROOM_NUMBER,
    }
  }),
)

/** 아직 반납되지 않은 대여 전체 (카페 기준) */
const activeRents = computed(() => toAdminRents(dataset.value))

const cabinets = computed<CabinetSlot[]>(() => {
  const gameById = new Map(dataset.value.games.map((game) => [game.id, game]))
  const holderByItem = new Map(
    activeRents.value.map((rent) => [rent.itemId, rent.roomNumber]),
  )
  const lastOpenByCabinet = new Map<number, number>()
  // cabinetOpens 는 최신순으로 정렬돼 있어 처음 만난 값이 마지막 개폐다
  for (const event of dataset.value.cabinetOpens) {
    if (!lastOpenByCabinet.has(event.cabinetId)) {
      lastOpenByCabinet.set(event.cabinetId, event.at)
    }
  }

  return dataset.value.items.map((item) => {
    const heldBy = holderByItem.get(item.itemId) ?? null
    return {
      cabinetId: item.cabinetId,
      itemId: item.itemId,
      gameId: item.gameId,
      gameName: gameById.get(item.gameId)?.name ?? '이름 미등록',
      itemStatus: heldBy === null ? 'AVAILABLE' : 'RENTED',
      doorState: doorStates.value.get(item.cabinetId) ?? 'CLOSED',
      lastOpenedAt: lastOpenByCabinet.get(item.cabinetId) ?? null,
      heldBy,
    }
  })
})

/** 기간 필터를 따르는 집계. 필터를 화면에 띄운 곳에서만 쓸 것. */
const stats = computed(() =>
  buildStats(dataset.value, ADMIN_ROOM_NUMBERS, range.value, statsClock.value),
)

/**
 * 항상 '오늘' 로 고정된 집계.
 *
 * 기간 선택 UI 가 없는 화면(방 현황의 요약 줄 등)이 `stats` 를 쓰면, 대시보드에서
 * '최근 30일' 을 골라 둔 상태로 넘어왔을 때 '오늘 누적 711팀' 같은 거짓말을 한다.
 * 필터를 보여 주지 않는 화면은 이쪽을 쓴다.
 */
const todayStats = computed(() =>
  buildStats(dataset.value, ADMIN_ROOM_NUMBERS, 'today', statsClock.value),
)

const aiLogs = computed<AiLogRow[]>(() => {
  const nameById = new Map(dataset.value.games.map((game) => [game.id, game.name]))
  return dataset.value.aiEvents.slice(0, AI_LOG_LIMIT).map((event) => ({
    id: event.id,
    kind: event.kind,
    roomNumber: event.roomNumber,
    gameName: nameById.get(event.gameId) ?? '이름 미등록',
    at: event.at,
    summary: event.summary,
    detail: event.detail,
  }))
})

/* ── 쓰기 동작 ─────────────────────────────────────────── */

/**
 * 입실. 화면 쪽 이용 이력에 데모 세션을 추가한다.
 * 이미 이용 중인 방이면 아무것도 하지 않는다.
 */
export async function checkIn(
  roomNumber: string,
  partySize: number,
): Promise<ActionResult> {
  const result: ActionResult = { synced: true, error: null }

  const already = dataset.value.sessions.some(
    (session) => session.roomNumber === roomNumber && session.endedAt === null,
  )
  if (already) return result

  dataset.value = {
    ...dataset.value,
    sessions: [
      ...dataset.value.sessions,
      {
        id: Math.max(0, ...dataset.value.sessions.map((s) => s.id)) + 1,
        roomNumber,
        startedAt: now.value,
        endedAt: null,
        partySize,
      },
    ],
  }
  return result
}

/**
 * 퇴실. 이용 이력 마감 + 그 방의 미반납 대여 전부 반납 + 대기 예약 전부 취소를
 * 화면 쪽 원자료에 반영한다. 여기서 대여 정리를 빼면 방은 비었는데 사물함은
 * 잠긴 상태로 남아 재고가 어긋난다.
 */
export async function checkOut(roomNumber: string): Promise<ActionResult> {
  const result: ActionResult = { synced: true, error: null }
  const endedAt = now.value

  const returning = dataset.value.rents.filter(
    (rent) => rent.roomNumber === roomNumber && rent.returnedAt === null,
  )

  dataset.value = {
    ...dataset.value,
    sessions: dataset.value.sessions.map((session) =>
      session.roomNumber === roomNumber && session.endedAt === null
        ? { ...session, endedAt }
        : session,
    ),
    rents: dataset.value.rents.map((rent) =>
      rent.roomNumber === roomNumber && rent.returnedAt === null
        ? { ...rent, returnedAt: endedAt }
        : rent,
    ),
    reservations: dataset.value.reservations.map((reservation) =>
      reservation.roomNumber === roomNumber && reservation.status === 'WAITING'
        ? { ...reservation, status: 'CANCELLED' as const }
        : reservation,
    ),
    // 반납도 사물함을 여는 행위라 개폐 이력에 남는다
    cabinetOpens: [
      ...returning.map((rent) => ({ cabinetId: rent.cabinetId, at: endedAt })),
      ...dataset.value.cabinetOpens,
    ],
  }

  return result
}

/**
 * 강제 반납 한 건. 손님이 반납 처리 없이 나가버린 대여를 관리자가 정리한다.
 *
 * 서버에는 개별 반납 엔드포인트가 없다 — 재고 복구는 퇴실(cleanUpRoom)에서만
 * 일어난다. 그래서 이 동작은 화면에만 반영되고, 실제 DB 를 고치려면 그 방을
 * 퇴실 처리해야 한다. 화면에서 그렇게 안내한다.
 */
export function forceReturn(rentId: number): void {
  const target = dataset.value.rents.find((rent) => rent.rentId === rentId)
  if (!target || target.returnedAt !== null) return

  const returnedAt = now.value
  dataset.value = {
    ...dataset.value,
    rents: dataset.value.rents.map((rent) =>
      rent.rentId === rentId ? { ...rent, returnedAt } : rent,
    ),
    cabinetOpens: [
      { cabinetId: target.cabinetId, at: returnedAt },
      ...dataset.value.cabinetOpens,
    ],
  }
}

/**
 * 사물함 강제 오픈. 브로커에 명령을 던지고 컨트롤러의 status 보고를 기다린다.
 *
 * 보고가 없으면 실패로 끝낸다 — 컨트롤러는 카드 태그로 열린 트랜잭션이 없으면
 * open 을 조용히 무시하므로(cabinetMqtt.ts 주석), '보냈으니 열렸다' 고 볼 수 없다.
 */
export function openCabinet(
  cabinetId: number,
  mode: 'receive' | 'return',
): boolean {
  // 브로커 주소가 없으면 보낼 곳이 없다. 조용히 넘어가면 호출한 화면이
  // '명령을 보냈습니다' 라고 거짓말을 하므로 실패를 돌려준다.
  if (!isCabinetMqttConfigured()) return false

  const attempt: CabinetOpenAttempt = {
    cabinetId,
    transactionId: publishCabinetOpen(cabinetId, mode),
    phase: 'waiting',
    reason: null,
    startedAt: Date.now(),
  }
  resolveAttempt(cabinetId, attempt)

  setTimeout(() => {
    const current = openAttempts.value.get(cabinetId)
    if (!current || current.transactionId !== attempt.transactionId) return
    if (current.phase !== 'waiting') return

    resolveAttempt(cabinetId, {
      ...current,
      phase: 'failed',
      reason:
        '컨트롤러가 응답하지 않았습니다. 카드 태그로 시작된 거래가 없으면 명령이 무시됩니다.',
    })
  }, OPEN_TIMEOUT_MS)

  return true
}

/** 카드 배지에 남은 결과 지우기 */
export function clearOpenAttempt(cabinetId: number): void {
  const next = new Map(openAttempts.value)
  next.delete(cabinetId)
  openAttempts.value = next
}

/** 데모 데이터 다시 만들기. 시연을 처음부터 돌릴 때 쓴다. */
export function regenerate(): void {
  dataset.value = createDemoDataset(ADMIN_ROOM_NUMBERS, now.value)
  doorStates.value = new Map()
  openAttempts.value = new Map()
}

/**
 * 자정을 넘기면 데이터셋을 다시 만든다. 씨앗이 날짜라서 그냥 두면
 * '오늘' 범위가 빈 채로 남는다(데모를 하루 넘게 켜 두는 경우).
 */
watch(statsClock, (current, previous) => {
  if (new Date(current).getDate() !== new Date(previous).getDate()) regenerate()
})

export function useAdminStore() {
  start()
  return {
    now,
    range,
    rooms,
    activeRents,
    cabinets,
    stats,
    todayStats,
    aiLogs,
    openAttempts,
    games: computed(() => dataset.value.games),
    reservations: computed(() => dataset.value.reservations),
    checkIn,
    checkOut,
    forceReturn,
    openCabinet,
    clearOpenAttempt,
    regenerate,
  }
}
