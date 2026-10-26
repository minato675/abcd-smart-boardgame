/**
 * 관리자 화면용 데모 데이터셋.
 *
 * **왜 목업인가.** inte-server 에는 통계·방목록·사물함 조회 API 가 하나도 없다
 * (있는 관리자 API 는 `/admin/room/update`, `/admin/room/checkin`, `/admin/room/checkout`
 * 세 개뿐이다). 그래서 화면이 읽을 값을 여기서 만든다.
 *
 * **집계는 진짜다.** 여기서 만드는 건 요약된 숫자가 아니라 원자료 —
 * 이용 이력(room_usage) · 대여(rent) · 예약(reservation) 행이다. 대시보드의 모든
 * 수치는 src/admin/stats.ts 가 이 행들을 실제로 집계해서 낸다. 그래서 관리자가
 * 화면에서 퇴실이나 강제 반납을 하면 통계가 실제로 따라 움직이고, 나중에 서버가
 * 같은 모양의 행을 주기 시작하면 집계 코드는 그대로 두고 이 파일만 지우면 된다.
 *
 * 행 모양은 DB 테이블(inte-server/src/main/resources/mapper/*.xml)을 그대로 따랐다.
 */

import type { Difficulty } from '@/types/game'
import type { AdminRentStatus } from './types'

export const MINUTE = 60_000
export const HOUR = 60 * MINUTE
export const DAY = 24 * HOUR

/** 데모가 만들어 두는 과거 기간. 대시보드의 '최근 30일' 이 이 값에 맞춰져 있다. */
export const HISTORY_DAYS = 30

/** 영업 시간. 입실은 이 사이에만 일어난다. */
const OPEN_HOUR = 11
const CLOSE_HOUR = 23

/* ── 원자료 행 ─────────────────────────────────────────── */

/** room_usage 한 행 */
export interface UsageSession {
  id: number
  roomNumber: string
  startedAt: number
  /** 아직 이용 중이면 null */
  endedAt: number | null
  /** 서버 스키마에 없는 값. 관리자가 입실 때 입력한 인원이다. */
  partySize: number
}

/** rent 한 행 */
export interface RentRecord {
  rentId: number
  sessionId: number
  roomNumber: string
  gameId: number
  itemId: number
  cabinetId: number
  rentedAt: number
  /** 미반납이면 null */
  returnedAt: number | null
  /** 미반납 건에서만 의미가 있다(반납된 행은 'RETURNED' 라 여기 오지 않는다) */
  status: AdminRentStatus
}

/** reservation 한 행 */
export interface ReservationRecord {
  reservationId: number
  roomNumber: string
  gameId: number
  reservedAt: number
  status: 'WAITING' | 'FULFILLED' | 'CANCELLED'
  fulfilledAt: number | null
}

/** cabinet_history 의 '열림' 이벤트 한 건 */
export interface CabinetOpenEvent {
  cabinetId: number
  at: number
}

/** board_game_item 한 행. 사본 하나가 사물함 한 칸을 차지한다. */
export interface ItemRecord {
  itemId: number
  cabinetId: number
  gameId: number
}

/** qna_log / mc_turn_log / mc_violation_log 를 한 줄로 합친 행 */
export interface AiEvent {
  id: number
  kind: 'QNA' | 'MC_TURN' | 'MC_VIOLATION'
  roomNumber: string
  gameId: number
  at: number
  summary: string
  detail: string | null
}

export interface GameSeed {
  id: number
  name: string
  category: string
  difficulty: Difficulty
  /** 상자에 적힌 플레이 시간(분) */
  boxPlayMinutes: number
  minPlayers: number
  maxPlayers: number
  copies: number
  /** 대여 추첨 가중치. 높을수록 자주 나간다. */
  weight: number
  /** AI 심판(카메라 판정)이 지원하는 게임인지 */
  mcSupported: boolean
}

export interface DemoDataset {
  games: GameSeed[]
  items: ItemRecord[]
  sessions: UsageSession[]
  rents: RentRecord[]
  reservations: ReservationRecord[]
  cabinetOpens: CabinetOpenEvent[]
  aiEvents: AiEvent[]
}

/* ── 카탈로그 ─────────────────────────────────────────── */

/**
 * 카페 보유 목록. 카테고리는 4종(전략·파티·추리·액션)으로 묶어 두었다 —
 * 카테고리 차트가 색 슬롯을 고정 순서로 쓸 수 있는 상한(5 + 기타)을 넘지 않게 한 것이다.
 */
const CATALOG: Omit<GameSeed, 'id'>[] = [
  { name: '루미큐브', category: '전략', difficulty: 'NORMAL', boxPlayMinutes: 60, minPlayers: 2, maxPlayers: 4, copies: 3, weight: 10, mcSupported: true },
  { name: '할리갈리', category: '액션', difficulty: 'EASY', boxPlayMinutes: 15, minPlayers: 2, maxPlayers: 6, copies: 4, weight: 9, mcSupported: false },
  { name: '스플렌더', category: '전략', difficulty: 'NORMAL', boxPlayMinutes: 30, minPlayers: 2, maxPlayers: 4, copies: 3, weight: 8, mcSupported: false },
  { name: '딕싯', category: '파티', difficulty: 'EASY', boxPlayMinutes: 30, minPlayers: 3, maxPlayers: 6, copies: 3, weight: 7, mcSupported: false },
  { name: '코드네임', category: '파티', difficulty: 'EASY', boxPlayMinutes: 20, minPlayers: 4, maxPlayers: 8, copies: 3, weight: 7, mcSupported: false },
  { name: '아줄', category: '전략', difficulty: 'NORMAL', boxPlayMinutes: 40, minPlayers: 2, maxPlayers: 4, copies: 2, weight: 6, mcSupported: false },
  { name: '카탄', category: '전략', difficulty: 'HARD', boxPlayMinutes: 90, minPlayers: 3, maxPlayers: 4, copies: 2, weight: 6, mcSupported: false },
  { name: '스텔라', category: '파티', difficulty: 'EASY', boxPlayMinutes: 30, minPlayers: 3, maxPlayers: 6, copies: 2, weight: 5, mcSupported: false },
  { name: '티켓 투 라이드', category: '전략', difficulty: 'NORMAL', boxPlayMinutes: 60, minPlayers: 2, maxPlayers: 5, copies: 2, weight: 5, mcSupported: false },
  { name: '텔레스트레이션', category: '파티', difficulty: 'EASY', boxPlayMinutes: 30, minPlayers: 4, maxPlayers: 8, copies: 2, weight: 5, mcSupported: false },
  { name: '카르카손', category: '전략', difficulty: 'NORMAL', boxPlayMinutes: 45, minPlayers: 2, maxPlayers: 5, copies: 2, weight: 4, mcSupported: false },
  { name: '뱅!', category: '파티', difficulty: 'NORMAL', boxPlayMinutes: 30, minPlayers: 4, maxPlayers: 7, copies: 2, weight: 4, mcSupported: false },
  { name: '젠가', category: '액션', difficulty: 'EASY', boxPlayMinutes: 15, minPlayers: 2, maxPlayers: 8, copies: 2, weight: 4, mcSupported: false },
  { name: '크라임씬', category: '추리', difficulty: 'HARD', boxPlayMinutes: 90, minPlayers: 3, maxPlayers: 6, copies: 1, weight: 3, mcSupported: false },
  { name: '셜록 홈즈 컨설팅 탐정', category: '추리', difficulty: 'HARD', boxPlayMinutes: 90, minPlayers: 1, maxPlayers: 8, copies: 1, weight: 2, mcSupported: false },
  { name: '세븐 원더스', category: '전략', difficulty: 'HARD', boxPlayMinutes: 45, minPlayers: 3, maxPlayers: 7, copies: 1, weight: 3, mcSupported: false },
]

/** 규칙 도우미에 실제로 들어올 법한 질문. 게임 종류와 무관하게 돌려 쓴다. */
const QNA_QUESTIONS = [
  '조커는 몇 장까지 낼 수 있어?',
  '처음에 몇 점 이상 내야 등록이 돼?',
  '점수 계산은 어떻게 해?',
  '같은 색으로만 이어도 되나요?',
  '패를 못 내면 어떻게 하나요?',
  '무승부일 때는 누가 이기는 거예요?',
  '카드를 몇 장씩 나눠 가져요?',
  '한 턴에 여러 번 행동할 수 있나요?',
]

const QNA_ANSWERS = [
  '조커는 세트에 몇 장이든 넣을 수 있지만, 한 세트에 같은 조커가 두 장 들어가지는 않습니다.',
  '첫 등록은 30점 이상이어야 하고, 이때는 손패만으로 만들어야 합니다.',
  '남은 손패의 숫자 합이 벌점이 됩니다. 조커는 30점으로 셉니다.',
  '같은 색이면 숫자가 연속이어야 하고, 숫자가 같으면 색이 모두 달라야 합니다.',
  '낼 수 없으면 더미에서 한 장을 가져오고 차례가 넘어갑니다.',
  '남은 손패 점수가 더 적은 쪽이 이깁니다.',
  '처음에 14장씩 나눠 가집니다.',
  '한 턴에는 한 번만 행동할 수 있습니다.',
]

/** AI 심판이 잡는 반칙. mc_violation_log.code / message 와 같은 모양이다. */
const MC_VIOLATIONS = [
  { code: 'INVALID_SET', message: '3장 미만의 세트가 테이블에 올라왔습니다.' },
  { code: 'DUPLICATE_COLOR', message: '같은 숫자 세트에 같은 색이 두 번 들어갔습니다.' },
  { code: 'FIRST_MELD_UNDER_30', message: '첫 등록 점수가 30점에 못 미칩니다.' },
  { code: 'TILE_TAKEN_BACK', message: '이미 등록된 타일을 손으로 되가져갔습니다.' },
]

/* ── 난수 ─────────────────────────────────────────────── */

/**
 * 씨앗을 받는 난수(mulberry32).
 *
 * Math.random 을 쓰면 새로고침할 때마다 '어제 방문 팀 수' 같은 과거 수치가 바뀌어서
 * 데모 중에 화면을 다시 열 수 없다. 오늘 날짜를 씨앗으로 삼아 하루 동안은 같은
 * 데이터가 나오게 하고, 날이 바뀌면 자연스럽게 다른 데이터가 되게 한다.
 */
function createRandom(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** [min, max] 정수 */
function randomInt(random: () => number, min: number, max: number): number {
  return min + Math.floor(random() * (max - min + 1))
}

function pick<T>(random: () => number, values: readonly T[]): T {
  return values[Math.floor(random() * values.length)] as T
}

/** 원본을 건드리지 않는 셔플(Fisher–Yates) */
function shuffled<T>(random: () => number, values: readonly T[]): T[] {
  const copy = [...values]
  for (let index = copy.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(random() * (index + 1))
    ;[copy[index], copy[swap]] = [copy[swap] as T, copy[index] as T]
  }
  return copy
}

/** 가중 추첨. weight 가 큰 게임이 자주 뽑힌다. */
function pickWeighted(random: () => number, games: GameSeed[]): GameSeed {
  const total = games.reduce((sum, game) => sum + game.weight, 0)
  let cursor = random() * total
  for (const game of games) {
    cursor -= game.weight
    if (cursor <= 0) return game
  }
  return games[games.length - 1] as GameSeed
}

/* ── 생성 ─────────────────────────────────────────────── */

export function startOfDay(timestamp: number): number {
  const date = new Date(timestamp)
  date.setHours(0, 0, 0, 0)
  return date.getTime()
}

/**
 * 요일별 혼잡도. 금·토가 붐비고 월·화가 한산한 실제 패턴을 흉내 낸다.
 * 인덱스는 Date#getDay (0=일).
 */
const WEEKDAY_LOAD = [1.15, 0.6, 0.65, 0.75, 0.9, 1.35, 1.5]

/**
 * 데이터셋 생성. `now` 기준으로 과거 HISTORY_DAYS 일치를 만들고,
 * 오늘치는 지금 시각까지만 만든다(미래에 입실한 팀이 있으면 안 된다).
 */
export function createDemoDataset(roomNumbers: string[], now: number): DemoDataset {
  const random = createRandom(startOfDay(now) / DAY)

  const games: GameSeed[] = CATALOG.map((seed, index) => ({ ...seed, id: index + 1 }))

  const items: ItemRecord[] = []
  for (const game of games) {
    for (let copy = 0; copy < game.copies; copy += 1) {
      // 사물함 번호는 사본이 등록된 순서대로 1번부터 채워진다
      items.push({ itemId: items.length + 1, cabinetId: items.length + 1, gameId: game.id })
    }
  }
  const itemsByGame = new Map<number, ItemRecord[]>()
  for (const item of items) {
    const bucket = itemsByGame.get(item.gameId) ?? []
    bucket.push(item)
    itemsByGame.set(item.gameId, bucket)
  }

  const sessions: UsageSession[] = []
  const rents: RentRecord[] = []
  const reservations: ReservationRecord[] = []
  const cabinetOpens: CabinetOpenEvent[] = []
  const aiEvents: AiEvent[] = []

  /**
   * 사본별로 '언제부터 언제까지 나가 있었나' 를 기록한다.
   *
   * 지금 나가 있는 사본만 기억하면 과거의 재고 경합이 사라져서 **예약이 한 건도
   * 생기지 않는다** — 예약은 원하는 게임의 사본이 그 시각에 전부 나가 있을 때만
   * 걸리기 때문이다. 구간으로 들고 있어야 어제 오후에 루미큐브 3벌이 동시에
   * 나가 있던 상황이 재현되고, 거기서 대기열 통계가 나온다.
   */
  const busyByItem = new Map<number, { from: number; to: number }[]>()

  const today = startOfDay(now)

  for (let dayOffset = HISTORY_DAYS - 1; dayOffset >= 0; dayOffset -= 1) {
    const dayStart = today - dayOffset * DAY
    const load = WEEKDAY_LOAD[new Date(dayStart).getDay()] ?? 1

    // 방 순서를 날마다 섞는다. 고정하면 늘 앞번호 방이 인기 게임을 먼저 집어가서
    // '6번 방만 예약을 건다' 는 없는 패턴이 통계에 생긴다.
    const order = shuffled(random, roomNumbers)

    order.forEach((roomNumber) => {
      /*
       * 방마다 첫 손님 시각을 크게 벌린다. 전 방이 11시쯤 같이 시작하면 체류
       * 시간이 비슷해서 하루 종일 위상이 맞은 채로 간다 — 어느 순간에는 전 방이
       * 차 있고 다음 순간에는 전 방이 비는, 실제로는 없는 모양이 된다.
       */
      const slot = roomNumbers.indexOf(roomNumber)
      let cursor =
        dayStart +
        OPEN_HOUR * HOUR +
        (slot * 17 + randomInt(random, 0, 55)) * MINUTE

      // 마지막 입실은 마감 30분 전까지 받는다
      while (cursor < dayStart + CLOSE_HOUR * HOUR - 30 * MINUTE) {
        // 오늘은 아직 오지 않은 시간에 손님을 앉히지 않는다
        if (cursor > now) break

        const stayMinutes = Math.round(randomInt(random, 80, 210) * (0.85 + load * 0.15))
        const plannedEnd = Math.min(cursor + stayMinutes * MINUTE, dayStart + CLOSE_HOUR * HOUR)
        const isOpen = plannedEnd > now

        const session: UsageSession = {
          id: sessions.length + 1,
          roomNumber,
          startedAt: cursor,
          endedAt: isOpen ? null : plannedEnd,
          partySize: randomInt(random, 2, 6),
        }
        sessions.push(session)

        appendSessionActivity({
          random,
          session,
          sessionEnd: isOpen ? now : plannedEnd,
          isOpen,
          games,
          itemsByGame,
          busyByItem,
          rents,
          reservations,
          cabinetOpens,
          aiEvents,
          now,
        })

        if (isOpen) break

        // 청소·정리 시간. 붐비는 날일수록 짧다. load 로 나누기만 하면 한산한 날의
        // 빈 시간이 두 시간까지 늘어나 방이 종일 비어 보이므로 나눗수에 하한을 둔다.
        cursor =
          plannedEnd +
          Math.round(randomInt(random, 10, 55) / Math.max(0.85, load)) * MINUTE
      }
    })
  }

  appendWaitingReservations({
    random,
    games,
    itemsByGame,
    busyByItem,
    sessions,
    rents,
    reservations,
    now,
  })

  // 화면은 항상 '최근 것부터' 보여준다. 정렬을 여기서 한 번 끝내 두면
  // 컴포넌트마다 다시 정렬할 필요가 없다.
  rents.sort((a, b) => b.rentedAt - a.rentedAt)
  reservations.sort((a, b) => b.reservedAt - a.reservedAt)
  aiEvents.sort((a, b) => b.at - a.at)
  cabinetOpens.sort((a, b) => b.at - a.at)

  return { games, items, sessions, rents, reservations, cabinetOpens, aiEvents }
}

/**
 * 지금 대기 중인(WAITING) 예약을 만든다.
 *
 * 세션 생성 루프에서는 '진행 중인 방이 마침 품절 게임을 고르는' 경우에만 대기가
 * 생겨서 사실상 한 건도 안 나온다. 그런데 지금 전량 대여된 게임이 있으면 그걸
 * 기다리는 방이 있는 게 자연스럽다 — 그 상태를 여기서 채운다.
 *
 * 서버는 방당 WAITING 예약을 하나로 제한하므로(reservation 유니크 제약)
 * 한 방이 두 건을 갖지 않게 한다.
 */
function appendWaitingReservations(context: {
  random: () => number
  games: GameSeed[]
  itemsByGame: Map<number, ItemRecord[]>
  busyByItem: Map<number, { from: number; to: number }[]>
  sessions: UsageSession[]
  rents: RentRecord[]
  reservations: ReservationRecord[]
  now: number
}): void {
  const { random, games, itemsByGame, busyByItem, sessions, rents, reservations, now } =
    context

  const openRooms = sessions
    .filter((session) => session.endedAt === null)
    .map((session) => session.roomNumber)
  const roomsWithReservation = new Set<string>()

  for (const game of games) {
    const copies = itemsByGame.get(game.id) ?? []
    if (copies.length === 0) continue

    // 지금 이 순간 비어 있는 사본이 하나라도 있으면 기다릴 이유가 없다
    const anyFree = copies.some((item) =>
      isItemFree(busyByItem, item.itemId, now, now + MINUTE),
    )
    if (anyFree || random() > 0.6) continue

    // 이미 그 게임을 들고 있는 방은 대기를 걸 수 없다(서버가 ALREADY_RENTED 로 막는다)
    const holders = new Set(
      rents
        .filter((rent) => rent.gameId === game.id && rent.returnedAt === null)
        .map((rent) => rent.roomNumber),
    )
    const candidate = openRooms.find(
      (room) => !holders.has(room) && !roomsWithReservation.has(room),
    )
    if (!candidate) continue

    roomsWithReservation.add(candidate)
    reservations.push({
      reservationId: reservations.length + 1,
      roomNumber: candidate,
      gameId: game.id,
      reservedAt: now - randomInt(random, 3, 40) * MINUTE,
      status: 'WAITING',
      fulfilledAt: null,
    })
  }
}

interface ActivityContext {
  random: () => number
  session: UsageSession
  /** 활동을 만들 수 있는 마지막 시각 (진행 중이면 now) */
  sessionEnd: number
  isOpen: boolean
  games: GameSeed[]
  itemsByGame: Map<number, ItemRecord[]>
  /** 사본별 대여 구간. 같은 사본이 두 방에 동시에 가는 것을 막는다. */
  busyByItem: Map<number, { from: number; to: number }[]>
  rents: RentRecord[]
  reservations: ReservationRecord[]
  cabinetOpens: CabinetOpenEvent[]
  aiEvents: AiEvent[]
  now: number
}

/** [from, to) 가 이미 기록된 구간과 겹치지 않는지 */
function isItemFree(
  busyByItem: Map<number, { from: number; to: number }[]>,
  itemId: number,
  from: number,
  to: number,
): boolean {
  const intervals = busyByItem.get(itemId)
  if (!intervals) return true
  return !intervals.some((interval) => from < interval.to && to > interval.from)
}

function markItemBusy(
  busyByItem: Map<number, { from: number; to: number }[]>,
  itemId: number,
  from: number,
  to: number,
): void {
  const intervals = busyByItem.get(itemId) ?? []
  intervals.push({ from, to })
  busyByItem.set(itemId, intervals)
}

/**
 * 이용 한 건 안에서 일어나는 일 — 대여 · 예약 · 사물함 개폐 · AI 사용 — 을 채운다.
 *
 * 한 팀은 보통 게임을 여러 개 바꿔 가며 논다. 그래서 대여를 세션 시작 직후 한 번에
 * 몰지 않고 체류 시간에 걸쳐 순차로 만든다 — 시간대별 사물함 개폐 수가 실제처럼 퍼진다.
 */
function appendSessionActivity(context: ActivityContext): void {
  // aiEvents 는 여기서 직접 쓰지 않는다 — appendAiUsage 가 context 로 받아 채운다
  const {
    random, session, sessionEnd, isOpen, games, itemsByGame,
    busyByItem, rents, reservations, cabinetOpens, now,
  } = context

  const stayMinutes = (sessionEnd - session.startedAt) / MINUTE
  // 대략 40분에 한 게임. 짧게 앉았다 가는 팀은 한 개도 못 빌린다.
  const rentCount = Math.max(0, Math.min(4, Math.round(stayMinutes / 45)))

  let cursor = session.startedAt + randomInt(random, 3, 12) * MINUTE
  const usedGames = new Set<number>()

  for (let index = 0; index < rentCount; index += 1) {
    if (cursor >= sessionEnd) break

    // 같은 팀이 같은 게임을 두 번 빌릴 수는 없다(서버가 ALREADY_RENTED 로 막는다)
    let game = pickWeighted(random, games)
    for (let retry = 0; retry < 4 && usedGames.has(game.id); retry += 1) {
      game = pickWeighted(random, games)
    }
    if (usedGames.has(game.id)) continue
    usedGames.add(game.id)

    // 실제 플레이 시간은 상자에 적힌 시간과 다르다 — 규칙 설명하느라 늘 더 걸린다
    const playMinutes = Math.round(game.boxPlayMinutes * (1.05 + random() * 0.65))
    const returnAt = cursor + playMinutes * MINUTE

    // 그 시간 동안 통째로 비어 있는 사본이 있어야 빌릴 수 있다
    const copies = itemsByGame.get(game.id) ?? []
    const free = copies.filter((item) =>
      isItemFree(busyByItem, item.itemId, cursor, returnAt),
    )

    // 한 벌도 없으면 대기열에 선다. 이게 예약 통계의 유일한 발생원이다.
    if (free.length === 0) {
      reservations.push({
        reservationId: reservations.length + 1,
        roomNumber: session.roomNumber,
        gameId: game.id,
        reservedAt: cursor,
        // 진행 중인 세션의 예약만 아직 대기 상태로 남는다
        status: isOpen ? 'WAITING' : random() < 0.55 ? 'FULFILLED' : 'CANCELLED',
        fulfilledAt: isOpen ? null : cursor + randomInt(random, 5, 40) * MINUTE,
      })
      cursor += randomInt(random, 20, 45) * MINUTE
      continue
    }

    const item = free[randomInt(random, 0, free.length - 1)] as ItemRecord
    const stillOut = returnAt > now
    markItemBusy(busyByItem, item.itemId, cursor, returnAt)

    // 픽업(카드 태그로 사물함이 열린다)
    cabinetOpens.push({ cabinetId: item.cabinetId, at: cursor + randomInt(random, 1, 4) * MINUTE })

    if (stillOut) {
      rents.push({
        rentId: rents.length + 1,
        sessionId: session.id,
        roomNumber: session.roomNumber,
        gameId: game.id,
        itemId: item.itemId,
        cabinetId: item.cabinetId,
        rentedAt: cursor,
        returnedAt: null,
        // 대여 직후 몇 분은 아직 사물함에서 꺼내기 전이다
        status: now - cursor < 6 * MINUTE ? 'RENT' : 'USING',
      })
    } else {
      rents.push({
        rentId: rents.length + 1,
        sessionId: session.id,
        roomNumber: session.roomNumber,
        gameId: game.id,
        itemId: item.itemId,
        cabinetId: item.cabinetId,
        rentedAt: cursor,
        returnedAt: returnAt,
        status: 'USING',
      })
      // 반납(다시 태그해서 사물함이 열린다)
      cabinetOpens.push({ cabinetId: item.cabinetId, at: returnAt })
    }

    appendAiUsage(context, game, cursor, Math.min(returnAt, sessionEnd))

    cursor = Math.min(returnAt, sessionEnd) + randomInt(random, 3, 15) * MINUTE
  }
}

/** 한 판 도는 동안 쌓이는 AI 사용 기록(규칙 질문 · 턴 판정 · 반칙) */
function appendAiUsage(
  context: ActivityContext,
  game: GameSeed,
  from: number,
  to: number,
): void {
  const { random, session, aiEvents } = context
  if (to <= from) return

  // 규칙 질문은 게임 종류를 가리지 않는다. 초반에 몰린다.
  const questionCount = random() < 0.45 ? randomInt(random, 1, 3) : 0
  for (let index = 0; index < questionCount; index += 1) {
    const pickIndex = randomInt(random, 0, QNA_QUESTIONS.length - 1)
    aiEvents.push({
      id: aiEvents.length + 1,
      kind: 'QNA',
      roomNumber: session.roomNumber,
      gameId: game.id,
      at: from + Math.round((to - from) * random() * 0.5),
      summary: QNA_QUESTIONS[pickIndex] as string,
      detail: QNA_ANSWERS[pickIndex] as string,
    })
  }

  // AI 심판은 카메라가 붙은 게임에서만 돈다
  if (!game.mcSupported || random() > 0.6) return

  const turns = randomInt(random, 6, 22)
  const step = (to - from) / (turns + 1)
  for (let turn = 1; turn <= turns; turn += 1) {
    aiEvents.push({
      id: aiEvents.length + 1,
      kind: 'MC_TURN',
      roomNumber: session.roomNumber,
      gameId: game.id,
      at: from + step * turn,
      summary: `${turn}번째 턴 판정`,
      detail: `테이블 타일 ${randomInt(random, 3, 28)}개 · 세트 ${randomInt(random, 1, 7)}개 인식`,
    })
  }

  if (random() < 0.45) {
    const violation = pick(random, MC_VIOLATIONS)
    aiEvents.push({
      id: aiEvents.length + 1,
      kind: 'MC_VIOLATION',
      roomNumber: session.roomNumber,
      gameId: game.id,
      at: from + step * randomInt(random, 1, turns),
      summary: violation.message,
      detail: violation.code,
    })
  }
}
