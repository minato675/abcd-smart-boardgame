/**
 * 원자료(room_usage · rent · reservation 행) → 대시보드 수치.
 *
 * 순수 함수만 둔다. 데이터가 목업이든 서버가 준 것이든 집계는 같아야 하고,
 * 서버에 `GET /admin/stats` 가 생기면 이 파일 대신 그 응답을 쓰면 된다
 * (반환 타입 StatsBundle 이 그대로 응답 계약이다).
 *
 * 집계 원칙 두 가지:
 * 1. **구간에 걸치는 건 시작 시각으로 센다.** 어제 입실해 오늘 나간 팀은 어제 팀이다.
 *    끝 시각으로 세면 심야 영업일에 오늘 수치가 부풀고, 양쪽으로 세면 합이 안 맞는다.
 * 2. **평균은 끝난 건으로만 낸다.** 아직 진행 중인 이용/대여를 '지금까지 40분' 으로
 *    평균에 넣으면 낮 시간대에 평균 체류가 실제보다 짧게 나온다.
 */

import { DAY, HOUR, MINUTE, startOfDay } from './demoData'
import type { DemoDataset, ReservationRecord, UsageSession } from './demoData'
import { STATS_RANGE_OPTIONS } from './types'
import type {
  AdminRent,
  Bucket,
  GameStatRow,
  StatsBundle,
  StatsRange,
} from './types'

/** 영업 시간. 시간대 차트의 x 축 범위다. */
const OPEN_HOUR = 11
const CLOSE_HOUR = 23

/** 카테고리 차트가 색 슬롯을 쓰는 상한. 이 밖은 '기타' 한 칸으로 접는다. */
const CATEGORY_SLOTS = 5

export function rangeDays(range: StatsRange): number {
  return STATS_RANGE_OPTIONS.find((option) => option.value === range)?.days ?? 1
}

/** 구간의 시작 시각. '최근 7일' 은 6일 전 0시부터 지금까지다(오늘 포함 7일). */
export function rangeStart(range: StatsRange, now: number): number {
  return startOfDay(now) - (rangeDays(range) - 1) * DAY
}

function within(timestamp: number, from: number, to: number): boolean {
  return timestamp >= from && timestamp <= to
}

function average(values: number[]): number | null {
  if (values.length === 0) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

/** 미반납 대여를 화면용 행으로. 사물함/게임 이름을 붙인다. */
export function toAdminRents(dataset: DemoDataset): AdminRent[] {
  const nameById = new Map(dataset.games.map((game) => [game.id, game.name]))
  return dataset.rents
    .filter((rent) => rent.returnedAt === null)
    .map((rent) => ({
      rentId: rent.rentId,
      roomNumber: rent.roomNumber,
      gameId: rent.gameId,
      gameName: nameById.get(rent.gameId) ?? '이름 미등록',
      itemId: rent.itemId,
      cabinetId: rent.cabinetId,
      status: rent.status,
      rentedAt: rent.rentedAt,
    }))
    .sort((a, b) => a.rentedAt - b.rentedAt)
}

/**
 * 방이 구간 안에서 실제로 손님을 받은 시간의 비율.
 *
 * 분모는 달력 시간 전체가 아니라 **영업 시간**이다(11~23시, 하루 12시간).
 * 24시간으로 나누면 문 닫은 새벽까지 '노는 시간' 으로 잡혀서 어느 방이든 50% 를
 * 못 넘고, 방끼리 비교하는 값으로 쓸모가 없어진다.
 */
function utilization(
  sessions: UsageSession[],
  from: number,
  to: number,
): number {
  const busyMs = sessions.reduce((sum, session) => {
    const start = Math.max(session.startedAt, from)
    const end = Math.min(session.endedAt ?? to, to)
    return sum + Math.max(0, end - start)
  }, 0)

  const days = Math.max(1, Math.ceil((to - from) / DAY))
  const openMs = days * (CLOSE_HOUR - OPEN_HOUR) * HOUR
  // 오늘이 아직 안 끝났으면 지나간 영업 시간까지만 분모로 쓴다
  const elapsedToday = Math.min(
    Math.max(0, to - (startOfDay(to) + OPEN_HOUR * HOUR)),
    (CLOSE_HOUR - OPEN_HOUR) * HOUR,
  )
  const denominator = openMs - ((CLOSE_HOUR - OPEN_HOUR) * HOUR - elapsedToday)

  return denominator <= 0 ? 0 : Math.min(1, busyMs / denominator)
}

/** '8/3' 처럼 짧은 날짜 라벨 */
function dayLabel(timestamp: number): string {
  const date = new Date(timestamp)
  return `${date.getMonth() + 1}/${date.getDate()}`
}

/** 영업시간 칸(11~22시)에 시각 목록을 떨어뜨린다 */
function bucketByHour(timestamps: number[]): Bucket[] {
  const counts = new Array<number>(CLOSE_HOUR - OPEN_HOUR).fill(0)
  for (const timestamp of timestamps) {
    const index = new Date(timestamp).getHours() - OPEN_HOUR
    if (index >= 0 && index < counts.length) {
      counts[index] = (counts[index] as number) + 1
    }
  }
  return counts.map((value, index) => ({ label: `${OPEN_HOUR + index}시`, value }))
}

/**
 * 증감률. 비교 대상이 0이면 null 이다 — 0에서 5로 늘어난 것을 '+500%' 라고 쓰면
 * 비율로서 의미가 없고, '+100%' 는 아예 틀린 값이다. 화면은 null 을 받으면
 * 증감 배지를 그리지 않는다.
 */
function deltaRatio(current: number, previous: number): number | null {
  return previous === 0 ? null : (current - previous) / previous
}

/**
 * 바로 앞 같은 길이 구간의 headline 값.
 *
 * 창을 통째로 days 만큼 뒤로 민다 — '오늘' 을 고른 경우 어제 **같은 시각까지** 와
 * 비교하게 된다. 어제 하루 전체와 비교하면 오전 11시에 늘 '-70%' 가 뜬다.
 */
function previousWindow(
  dataset: DemoDataset,
  from: number,
  to: number,
  days: number,
): { teams: number; visitors: number; rents: number } {
  const shift = days * DAY
  const prevFrom = from - shift
  const prevTo = to - shift

  const sessions = dataset.sessions.filter((session) =>
    within(session.startedAt, prevFrom, prevTo),
  )
  return {
    teams: sessions.length,
    visitors: sessions.reduce((sum, session) => sum + session.partySize, 0),
    rents: dataset.rents.filter((rent) => within(rent.rentedAt, prevFrom, prevTo))
      .length,
  }
}

export function buildStats(
  dataset: DemoDataset,
  roomNumbers: string[],
  range: StatsRange,
  now: number,
): StatsBundle {
  const from = rangeStart(range, now)
  const to = now
  const days = rangeDays(range)

  const sessions = dataset.sessions.filter((session) =>
    within(session.startedAt, from, to),
  )
  const rents = dataset.rents.filter((rent) => within(rent.rentedAt, from, to))
  const reservations = dataset.reservations.filter((reservation) =>
    within(reservation.reservedAt, from, to),
  )
  const cabinetOpens = dataset.cabinetOpens.filter((event) =>
    within(event.at, from, to),
  )
  const aiEvents = dataset.aiEvents.filter((event) => within(event.at, from, to))

  const closedSessions = sessions.filter((session) => session.endedAt !== null)
  const returnedRents = rents.filter((rent) => rent.returnedAt !== null)

  /* ── 헤드라인 ─────────────────────────────────────── */

  const roomsInUse = dataset.sessions.filter(
    (session) => session.endedAt === null,
  ).length

  const avgStayMinutes = average(
    closedSessions.map(
      (session) => ((session.endedAt as number) - session.startedAt) / MINUTE,
    ),
  )
  const avgPlayMinutes = average(
    returnedRents.map(
      (rent) => ((rent.returnedAt as number) - rent.rentedAt) / MINUTE,
    ),
  )

  const fulfilled = reservations.filter(
    (reservation) => reservation.status === 'FULFILLED',
  ).length

  /* ── 시간대별 입실 ─────────────────────────────────── */

  const byHour = bucketByHour(sessions.map((session) => session.startedAt))
  const rentsByHour = bucketByHour(rents.map((rent) => rent.rentedAt))

  /* ── 일자별 추이 ───────────────────────────────────── */

  const teamsByDay: Bucket[] = []
  const rentsByDay: Bucket[] = []
  for (let offset = days - 1; offset >= 0; offset -= 1) {
    const dayFrom = startOfDay(now) - offset * DAY
    const dayTo = dayFrom + DAY
    const label = dayLabel(dayFrom)
    teamsByDay.push({
      label,
      value: sessions.filter((session) =>
        within(session.startedAt, dayFrom, dayTo - 1),
      ).length,
    })
    rentsByDay.push({
      label,
      value: rents.filter((rent) => within(rent.rentedAt, dayFrom, dayTo - 1))
        .length,
    })
  }

  /* ── 게임별 집계 ───────────────────────────────────── */

  const gameRows: GameStatRow[] = dataset.games
    .map((game) => {
      const gameRents = rents.filter((rent) => rent.gameId === game.id)
      const gameReturned = gameRents.filter((rent) => rent.returnedAt !== null)
      const playMinutes = gameReturned.map(
        (rent) => ((rent.returnedAt as number) - rent.rentedAt) / MINUTE,
      )
      const lastRentedAt = gameRents.reduce<number | null>(
        (latest, rent) => (latest === null || rent.rentedAt > latest ? rent.rentedAt : latest),
        null,
      )

      return {
        gameId: game.id,
        name: game.name,
        category: game.category,
        difficulty: game.difficulty,
        totalCount: game.copies,
        rentCount: gameRents.length,
        totalPlayMinutes: playMinutes.reduce((sum, value) => sum + value, 0),
        avgPlayMinutes: average(playMinutes),
        boxPlayMinutes: game.boxPlayMinutes,
        reservationCount: reservations.filter(
          (reservation) => reservation.gameId === game.id,
        ).length,
        turnsPerCopy: gameRents.length / game.copies,
        lastRentedAt,
      }
    })
    .sort((a, b) => b.rentCount - a.rentCount)

  const topGames: Bucket[] = gameRows
    .slice(0, 8)
    .map((row) => ({ label: row.name, value: row.rentCount }))

  /* ── 카테고리 · 난이도 ─────────────────────────────── */

  const categoryTotals = new Map<string, number>()
  for (const row of gameRows) {
    categoryTotals.set(
      row.category,
      (categoryTotals.get(row.category) ?? 0) + row.rentCount,
    )
  }
  const sortedCategories = [...categoryTotals.entries()].sort(
    (a, b) => b[1] - a[1],
  )
  const byCategory: Bucket[] = sortedCategories
    .slice(0, CATEGORY_SLOTS)
    .map(([label, value]) => ({ label, value }))
  const tail = sortedCategories.slice(CATEGORY_SLOTS)
  if (tail.length > 0) {
    // 색 슬롯을 새로 만들지 않고 '기타' 한 칸으로 접는다
    byCategory.push({
      label: '기타',
      value: tail.reduce((sum, [, value]) => sum + value, 0),
    })
  }

  // 난이도는 순서가 의미를 가진다(쉬움 → 어려움). 값 순으로 정렬하면 안 된다.
  const byDifficulty: Bucket[] = (
    [
      ['EASY', '쉬움'],
      ['NORMAL', '보통'],
      ['HARD', '어려움'],
    ] as const
  ).map(([key, label]) => ({
    label,
    value: gameRows
      .filter((row) => row.difficulty === key)
      .reduce((sum, row) => sum + row.rentCount, 0),
  }))

  /* ── 방별 가동률 ───────────────────────────────────── */

  const roomUtilization: Bucket[] = roomNumbers.map((roomNumber) => ({
    label: `${roomNumber}번 방`,
    value: utilization(
      dataset.sessions.filter((session) => session.roomNumber === roomNumber),
      from,
      to,
    ),
  }))

  /* ── 예약 퍼널 ─────────────────────────────────────── */

  const waiting = dataset.reservations.filter(
    (reservation: ReservationRecord) => reservation.status === 'WAITING',
  ).length

  const visitors = sessions.reduce((sum, session) => sum + session.partySize, 0)
  const previous = previousWindow(dataset, from, to, days)

  return {
    range,
    from,
    to,
    teams: sessions.length,
    visitors,
    rents: rents.length,
    delta: {
      teams: deltaRatio(sessions.length, previous.teams),
      visitors: deltaRatio(visitors, previous.visitors),
      rents: deltaRatio(rents.length, previous.rents),
    },
    roomsInUse,
    roomsTotal: roomNumbers.length,
    avgStayMinutes,
    avgPlayMinutes,
    rentsPerTeam: sessions.length === 0 ? 0 : rents.length / sessions.length,
    turnsPerRoom:
      roomNumbers.length === 0 ? 0 : sessions.length / roomNumbers.length,
    reservations: reservations.length,
    reservationsFulfilled: fulfilled,
    fulfillRate: reservations.length === 0 ? null : fulfilled / reservations.length,
    reservationsWaiting: waiting,
    cabinetOpens: cabinetOpens.length,
    mcSessions: countMcSessions(aiEvents),
    qnaQuestions: aiEvents.filter((event) => event.kind === 'QNA').length,
    mcViolations: aiEvents.filter((event) => event.kind === 'MC_VIOLATION').length,
    mcTurns: aiEvents.filter((event) => event.kind === 'MC_TURN').length,
    byHour,
    rentsByHour,
    teamsByDay,
    rentsByDay,
    topGames,
    byCategory,
    byDifficulty,
    roomUtilization,
    reservationFunnel: [
      { label: '예약 발생', value: reservations.length },
      { label: '반납 알림', value: fulfilled + waiting },
      { label: '대여 성사', value: fulfilled },
    ],
    gameRows,
  }
}

/**
 * AI 심판 '세션' 수. mc_turn_log 에는 세션 id 가 있지만 여기 원자료에는 없어서,
 * 같은 방·같은 게임의 턴 기록이 30분 넘게 끊기면 다른 판으로 본다.
 * (서버 통계 API 가 생기면 COUNT(DISTINCT session_id) 로 대체될 값이다.)
 */
function countMcSessions(events: { kind: string; roomNumber: string; gameId: number; at: number }[]): number {
  const turns = events
    .filter((event) => event.kind === 'MC_TURN')
    .sort((a, b) => a.at - b.at)

  const lastSeen = new Map<string, number>()
  let sessions = 0
  for (const turn of turns) {
    const key = `${turn.roomNumber}:${turn.gameId}`
    const previous = lastSeen.get(key)
    if (previous === undefined || turn.at - previous > 30 * MINUTE) sessions += 1
    lastSeen.set(key, turn.at)
  }
  return sessions
}
