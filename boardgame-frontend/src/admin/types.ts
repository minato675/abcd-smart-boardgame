/**
 * 관리자 화면이 쓰는 도메인 타입.
 *
 * 손님 화면(src/types/game.ts)과 일부러 분리한다 — 관리자는 '우리 방' 이 아니라
 * 카페 전체를 보고, 같은 단어(대여·예약)가 다른 범위를 가리킨다. 한 타입을 억지로
 * 공유하면 roomNumber 가 있는지 없는지로 계속 갈라져서 양쪽 다 읽기 어려워진다.
 *
 * 필드 이름은 DB 컬럼(inte-server/src/main/resources/mapper/*.xml)을 따랐다.
 * 나중에 통계 API 가 생기면 이 타입이 그대로 응답 계약이 되도록 맞춰 둔 것이다.
 * 시각 값은 전부 epoch ms 다(Date 객체를 reactive 에 넣으면 비교가 지저분해진다).
 */

import type { Difficulty } from '@/types/game'

/** room.status. 서버는 소문자로 저장하지만 API 는 대문자로 주고받는다. */
export type RoomStatus = 'USE' | 'EMPTY'

/** 한 방의 현재 상태 = room + 열려 있는 room_usage 한 건 */
export interface AdminRoom {
  roomNumber: string
  /** 화면 표시용 이름. 서버로 나가지 않는다. */
  label: string
  capacity: number
  status: RoomStatus
  /** 입실 시각(room_usage.start_time). EMPTY 면 null */
  startedAt: number | null
  /** 직전 퇴실 시각. 회전 간격을 보여줄 때 쓴다. */
  lastEndedAt: number | null
  /** 입실 때 받은 인원. 서버 스키마에 없어서 관리자 화면이 들고 있는 값이다. */
  partySize: number | null
  /**
   * 이 태블릿이 설치된 방인지(VITE_ROOM_NUMBER 와 일치).
   * 손님 화면과 상태가 실제로 연동되는 유일한 방이라 화면에서 표시해 준다.
   */
  isLocal: boolean
}

/** rent.status 중 아직 끝나지 않은 두 상태. 손님 화면의 RentStatus 와 같은 값이다. */
export type AdminRentStatus = 'RENT' | 'USING'

/** 아직 반납되지 않은 대여 한 건 (방 무관, 카페 전체) */
export interface AdminRent {
  rentId: number
  roomNumber: string
  gameId: number
  gameName: string
  /** 배정된 물리 사본 */
  itemId: number
  /** 그 사본이 들어 있는 사물함 */
  cabinetId: number
  status: AdminRentStatus
  rentedAt: number
}

/** board_game_item.status */
export type ItemStatus = 'AVAILABLE' | 'RENTED'

/** cabinet.status + 컨트롤러가 FAULT 로 빠진 경우 */
export type DoorState = 'CLOSED' | 'OPEN' | 'FAULT'

/** 사물함 한 칸 = 사본 하나. cabinet 과 board_game_item 을 합쳐 본 것이다. */
export interface CabinetSlot {
  cabinetId: number
  itemId: number
  gameId: number
  gameName: string
  itemStatus: ItemStatus
  doorState: DoorState
  /** 마지막 개폐 시각(cabinet_history) */
  lastOpenedAt: number | null
  /** 이 사본을 들고 나간 방. AVAILABLE 이면 null */
  heldBy: string | null
}

/**
 * 강제 오픈 한 번의 진행 상태.
 *
 * `waiting` 이 따로 있는 이유: 명령을 발행했다는 것과 문이 열렸다는 것은 다른
 * 사실이다. 컨트롤러가 status 를 올려 주기 전까지는 둘 중 어느 쪽인지 알 수 없다.
 */
export type CabinetOpenPhase = 'waiting' | 'opened' | 'failed'

export interface CabinetOpenAttempt {
  cabinetId: number
  transactionId: string
  phase: CabinetOpenPhase
  /** 실패했을 때 컨트롤러가 준 이유 또는 우리가 판단한 이유 */
  reason: string | null
  startedAt: number
}

/* ── 통계 ─────────────────────────────────────────────── */

/** 필터 한 줄이 정하는 집계 구간. 대시보드 전체가 같은 값을 본다. */
export type StatsRange = 'today' | 'week' | 'month'

export const STATS_RANGE_OPTIONS: { value: StatsRange; label: string; days: number }[] = [
  { value: 'today', label: '오늘', days: 1 },
  { value: 'week', label: '최근 7일', days: 7 },
  { value: 'month', label: '최근 30일', days: 30 },
]

/** 보드게임 한 종의 이용 실적 */
export interface GameStatRow {
  gameId: number
  name: string
  category: string
  difficulty: Difficulty | null
  /** 보유 사본 수 */
  totalCount: number
  /** 구간 내 대여 건수 */
  rentCount: number
  /** 구간 내 실제 플레이 시간 합(분). rent.play_time_sec 을 더한 값이다. */
  totalPlayMinutes: number
  /** 반납까지 끝난 건 기준 평균 플레이 시간(분) */
  avgPlayMinutes: number | null
  /** 상자에 적힌 플레이 시간(분). 실측과 비교하는 기준선이다. */
  boxPlayMinutes: number | null
  /** 구간 내 이 게임에 걸린 예약 수 */
  reservationCount: number
  /** 사본 하나당 대여 횟수 — 재고를 늘릴지 판단하는 값 */
  turnsPerCopy: number
  lastRentedAt: number | null
}

/** x 축 한 칸 */
export interface Bucket {
  label: string
  value: number
}

/** 예약 퍼널의 한 단계 */
export interface FunnelStage {
  label: string
  value: number
}

/** 대시보드가 한 번에 그리는 값 전부. 통계 API 가 생기면 이게 그 응답이 된다. */
export interface StatsBundle {
  range: StatsRange
  /** 집계 구간 시작 (epoch ms) */
  from: number
  /** 집계 구간 끝 = 지금 */
  to: number

  /* 헤드라인 */
  /** 구간 내 이용 팀 수(room_usage 건수) */
  teams: number
  /** 구간 내 방문 인원 합 */
  visitors: number
  /** 구간 내 대여 건수 */
  rents: number
  /** 지금 이용 중인 방 수 */
  roomsInUse: number
  /** 전체 방 수 */
  roomsTotal: number
  /** 마감된 이용건의 평균 체류 시간(분) */
  avgStayMinutes: number | null
  /** 반납된 대여의 평균 플레이 시간(분) */
  avgPlayMinutes: number | null
  /** 팀당 평균 대여 게임 수 */
  rentsPerTeam: number
  /** 방 하나가 구간 동안 받은 평균 팀 수 */
  turnsPerRoom: number
  /** 구간 내 예약 발생 / 이행 */
  reservations: number
  reservationsFulfilled: number
  /** 이행률(0~1). 예약이 0건이면 null */
  fulfillRate: number | null
  /** 지금 대기 중인 예약 */
  reservationsWaiting: number
  /** 구간 내 사물함 개폐 횟수 */
  cabinetOpens: number
  /** 구간 내 AI 심판 세션 수 */
  mcSessions: number
  /** 구간 내 규칙 질문 수 */
  qnaQuestions: number
  /** 구간 내 AI 심판이 잡은 반칙 수 */
  mcViolations: number
  /** 구간 내 턴 판정 기록 수. 한 판에 수십 건씩 쌓인다. */
  mcTurns: number

  /**
   * 바로 앞 같은 길이 구간 대비 증감률(-1 ~ ). 비교 대상이 0이면 null —
   * 0에서 늘어난 걸 '+∞%' 나 '+100%' 로 쓰면 둘 다 거짓말이다.
   */
  delta: {
    teams: number | null
    visitors: number | null
    rents: number | null
  }

  /* 시계열 · 분포 */
  /** 시간대별 입실 팀 수 (영업시간 11~23시) */
  byHour: Bucket[]
  /** 시간대별 대여 건수. byHour 와 같은 x 축을 쓴다. */
  rentsByHour: Bucket[]
  /** 일자별 이용 팀 수. range=today 면 오늘 한 점만 나온다. */
  teamsByDay: Bucket[]
  /** 일자별 대여 건수. teamsByDay 와 같은 x 축을 공유한다. */
  rentsByDay: Bucket[]
  /** 이용 횟수 상위 게임 */
  topGames: Bucket[]
  /** 카테고리별 대여 비중. 5위 밖은 '기타'로 접는다. */
  byCategory: Bucket[]
  /** 난이도별 대여 수. EASY→HARD 순서가 의미를 가진다. */
  byDifficulty: Bucket[]
  /** 방별 가동률(0~1) */
  roomUtilization: Bucket[]
  /** 예약 퍼널 */
  reservationFunnel: FunnelStage[]

  /** 게임별 상세 표 */
  gameRows: GameStatRow[]
}

/* ── AI 사용 로그 ─────────────────────────────────────── */

export type AiLogKind = 'QNA' | 'MC_TURN' | 'MC_VIOLATION'

export const AI_LOG_LABELS: Record<AiLogKind, string> = {
  QNA: '규칙 질문',
  MC_TURN: '턴 판정',
  MC_VIOLATION: '반칙 감지',
}

/** qna_log / mc_turn_log / mc_violation_log 를 한 줄로 합쳐 본 것 */
export interface AiLogRow {
  id: number
  kind: AiLogKind
  roomNumber: string
  gameName: string
  at: number
  /** 목록에 보이는 한 줄 (질문 / 판정 요약 / 반칙 메시지) */
  summary: string
  /** 펼쳤을 때 보이는 본문 (답변 / 테이블 상태 / 반칙 코드) */
  detail: string | null
}
