/**
 * 화면에서 쓰는 보드게임 도메인 타입.
 *
 * 서버 응답 원본은 src/api/dto.ts 에 있고, 변환은 src/api/mappers.ts 가 한다.
 * 서버 컬럼 상당수가 nullable 이므로 표시용 헬퍼가 null 을 반드시 처리한다.
 */

export const DIFFICULTIES = ['EASY', 'NORMAL', 'HARD'] as const

export type Difficulty = (typeof DIFFICULTIES)[number]

export const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  EASY: '쉬움',
  NORMAL: '보통',
  HARD: '어려움',
}

/** 서버 category 테이블의 행. 이름은 DB 값이므로 고정 목록이 아니다. */
export interface GameCategory {
  id: number
  name: string
}

/** 목록 조회(GET /boardgame)로 얻을 수 있는 범위 */
export interface BoardGame {
  id: number
  name: string
  /** 게임당 여러 개일 수 있고, 하나도 없을 수도 있다(LEFT JOIN) */
  categories: GameCategory[]
  /** 추천 인원 하한 */
  minPlayers: number | null
  /** 추천 인원 상한 */
  maxPlayers: number | null
  /** 플레이 시간(분) */
  playTimeMinutes: number | null
  /** 서버가 값을 주지 않거나 알 수 없는 값이면 null */
  difficulty: Difficulty | null
  /** 카드의 한 줄 설명. 등록되지 않았으면 null */
  description: string | null
  /** null 이면 이름 첫 글자 플레이스홀더를 그린다 */
  thumbnailUrl: string | null
  /** 보유 사본 수 */
  totalCount: number
  /** 지금 대여 가능한 사본 수 */
  availableCount: number
  /** availableCount > 0 — src/api/mappers.ts 에서만 계산한다 */
  available: boolean
}

/** 상세정보 화면의 '게임 방법' 단계 */
export interface GameStep {
  /** 서버 howToPlay 가 '제목: 설명' 형태가 아니면 null */
  title: string | null
  description: string
}

/** 상세 조회(GET /boardgame/{id})에만 있는 필드까지 */
export interface BoardGameDetail extends BoardGame {
  /** 서버 원본 문자열. steps 파싱이 어긋났을 때 확인용으로 남긴다. */
  howToPlay: string | null
  steps: GameStep[]
  /** 이 게임이 반납되기를 기다리는 팀 수(방 무관) */
  waitingCount: number
}

/* ── 필터 ─────────────────────────────────────────────── */

/** 카테고리는 이름이 아니라 categoryId 로 비교한다(이름은 중복될 수 있다) */
export type CategoryFilter = 'all' | number

/** 상황별 빠른 칩. 인원 칩보다 실제 상황('처음이에요')에 가깝다. */
export type QuickFilter = 'none' | 'easy' | 'short' | 'available'

export const QUICK_FILTER_OPTIONS: { value: QuickFilter; label: string }[] = [
  { value: 'easy', label: '처음이에요' },
  { value: 'short', label: '30분 안에' },
  { value: 'available', label: '지금 가능' },
]

/** 'short' 칩의 기준 플레이 시간(분) */
export const SHORT_PLAY_MINUTES = 30

export interface GameFilter {
  keyword: string
  category: CategoryFilter
  quick: QuickFilter
}

export function createEmptyFilter(): GameFilter {
  return { keyword: '', category: 'all', quick: 'none' }
}

/* ── 대여 ─────────────────────────────────────────────── */

/**
 * 서버 rent.status 중 아직 끝나지 않은 두 상태.
 *
 * - `RENT`  대여 버튼을 눌렀지만 아직 사물함에서 꺼내지 않았다.
 * - `USING` 카드를 태그해 사물함을 열고 닫았다 = 지금 테이블에서 쓰고 있다.
 *
 * 전이는 카드 태그 → MQTT → 서버(CabinetService)에서만 일어난다. 태블릿은 이 상태를
 * 추측할 수 없고 GET /rent 로 물어봐야 한다. `RETURNED` 는 그 응답에 오지 않는다.
 */
export type RentStatus = 'RENT' | 'USING'

/** 우리 방이 아직 반납하지 않은 대여 한 건 */
export interface RoomRent {
  id: number
  gameId: number
  gameName: string
  /** 열어야 하는 사물함. 서버가 사본을 붙이지 못한 경우 null */
  cabinetId: number | null
  status: RentStatus
}

/* ── 예약 ─────────────────────────────────────────────── */

/** 서버 reservation.status 와 동일 */
export type ReservationStatus = 'WAITING' | 'FULFILLED' | 'CANCELLED'

/**
 * 예약 = 지금 대여 중인 게임이 반납되기를 기다리는 줄.
 * 내가 가진 게임을 반납하겠다는 뜻이 아니다.
 *
 * 반납되면 **대기 1번인 방에게만** 알림이 온다(ReservationAlert). 다만 그 알림이 사본을
 * 붙잡아 두지는 않아서, 답하기 전에 예약을 걸지 않은 방이 먼저 눌러 가져갈 수는 있다.
 * 화면 문구가 '먼저 빌릴 수 있다' 고 단정하면 안 되는 이유다(reservationWaitLabel 참고).
 */
export interface Reservation {
  id: number
  gameId: number
  gameName: string
  status: ReservationStatus
  /** 예약 생성 응답에만 채워진다. 목록 조회로 복원한 경우 null. */
  waitingRank: number | null
}

/**
 * 예약한 게임이 반납됐다는 알림.
 * 브로커의 `/room/{roomNumber}/reservation/ready` 페이로드를 화면용으로 옮긴 것이다.
 *
 * 서버(inte-server ReservationNotifyService)는 이 알림을 보낸 뒤 timeoutSec 만큼 응답을
 * 기다리고, 그때까지 대여도 취소도 없으면 예약을 취소하고 다음 대기자에게 넘긴다.
 * 그래서 화면 카운트다운은 장식이 아니라 실제 서버 타이머를 비추는 값이다.
 */
export interface ReservationAlert {
  /** 취소 요청에 그대로 쓴다 */
  reservationId: number
  gameId: number
  gameName: string
  /** 서버가 이 예약을 취소하기까지 주는 시간(초) */
  timeoutSec: number
}

/* ── 화면에 그리는 게임 상태 ────────────────────────────── */

/**
 * 카드/상세가 그리는 게임 하나의 상태.
 *
 * `available` 하나로는 '내가 빌려서 재고가 없는 것' 과 '다른 팀이 빌려서 없는 것' 이
 * 구분되지 않아 예약 버튼이 잘못 뜬다(서버는 두 경우 모두 ALREADY_RENTED 로 거절한다).
 */
export type GameState =
  /** 우리 방이 지금 쓰고 있다 (rent.status = USING) */
  | 'using'
  /** 우리 방이 대여했지만 아직 사물함에서 꺼내지 않았다 (rent.status = RENT) */
  | 'pickup'
  /** 우리 방이 대기를 걸어뒀다 (reservation.status = WAITING) */
  | 'reserved'
  /** 남은 사본이 있어 지금 대여할 수 있다 */
  | 'available'
  /** 다른 팀이 다 빌려갔다 — 예약할 수 있는 유일한 상태 */
  | 'rentedOut'

/**
 * 상태 판정. **우리 방 상태가 재고 수보다 먼저다** —
 * 사본이 여럿이라 availableCount > 0 이어도 내가 이미 들고 있으면 서버가 재대여를 막는다.
 */
export function resolveGameState(
  game: Pick<BoardGame, 'available'>,
  rent: RoomRent | null,
  reserved: boolean,
): GameState {
  if (rent) return rent.status === 'USING' ? 'using' : 'pickup'
  if (reserved) return 'reserved'
  return game.available ? 'available' : 'rentedOut'
}

export const GAME_STATE_LABELS: Record<GameState, string> = {
  using: '사용 중',
  pickup: '대여 완료',
  reserved: '예약 완료',
  available: '대여 가능',
  rentedOut: '대여 중',
}

/** 액션 버튼 문구. using 만 요청이 아니라 안내를 연다. */
export const GAME_ACTION_LABELS: Record<GameState, string> = {
  using: '반납 방법',
  pickup: '대여 중',
  reserved: '예약 완료',
  available: '대여하기',
  rentedOut: '빌리기 예약',
}

/** 서버에 대여/예약 요청을 보낼 수 있는 상태인지 */
export function isActionable(state: GameState): boolean {
  return state === 'available' || state === 'rentedOut'
}

/**
 * 버튼이 안내(반납 방법)를 여는 상태인지.
 *
 * 대여 직후(pickup)는 손님이 로비에서 게임을 받아가므로 태블릿이 안내할 게 없다 —
 * 버튼은 '대여 중' 으로 비활성화되고, 안내가 필요한 건 반납뿐이다.
 */
export function isGuided(state: GameState): boolean {
  return state === 'using'
}

/* ── 표시용 헬퍼 ───────────────────────────────────────── */
/* 구조적 파라미터를 받아 BoardGame / BoardGameDetail 양쪽에 모두 쓰인다 */

export function difficultyLabel(game: Pick<BoardGame, 'difficulty'>): string {
  return game.difficulty ? DIFFICULTY_LABELS[game.difficulty] : '난이도 미등록'
}

export function categoryLabel(game: Pick<BoardGame, 'categories'>): string {
  return game.categories[0]?.name ?? '기타'
}

export function playerRangeLabel(
  game: Pick<BoardGame, 'minPlayers' | 'maxPlayers'>,
): string {
  const { minPlayers: min, maxPlayers: max } = game
  if (min === null && max === null) return '인원 미등록'
  if (min === null) return `${max}명 이하`
  if (max === null) return `${min}명 이상`
  return min === max ? `${min}명` : `${min}-${max}명`
}

export function playTimeLabel(
  game: Pick<BoardGame, 'playTimeMinutes'>,
): string {
  return game.playTimeMinutes === null
    ? '시간 미등록'
    : `${game.playTimeMinutes}분`
}

/**
 * 예약 대기 상태를 알리는 짧은 문구. 카드/현황바가 같은 말을 하도록 여기서만 만든다.
 *
 * 순번을 알려줄 뿐 '먼저 빌릴 수 있다' 고 약속하지 않는다 — 서버가 대기열을 강제하지 않아
 * 지킬 수 없는 약속이다(Reservation 주석 참고).
 *
 * waitingRank 는 예약 생성 응답에만 담기고 목록 조회로 복원하면 null 이라
 * (dto.ts ReservationResponse), 새로고침 이후에는 순번 없는 문구로 물러난다.
 */
export function reservationWaitLabel(waitingRank: number | null): string {
  return waitingRank === null
    ? '반납되면 알려드려요'
    : `대기 ${waitingRank}번째예요`
}

/** 카드에 넣는 한 줄 요약 — 설명의 첫 문장만 잘라 쓴다 */
export function summaryLine(game: Pick<BoardGame, 'description'>): string {
  if (!game.description) return '설명이 아직 등록되지 않았습니다.'
  const first = game.description.match(/^[^.!?]+[.!?]/)
  return (first ? first[0] : game.description).trim()
}
