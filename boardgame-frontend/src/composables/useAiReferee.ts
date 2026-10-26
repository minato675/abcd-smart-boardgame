import { computed, ref } from 'vue'
import {
  analyzeMc,
  fetchLatestTurnLog,
  fetchMcSession,
  finishMc,
  finishPlayerMc,
  startMc,
  type LatestTurnLog,
  type McTurnResult,
} from '@/api/mc'
import { isApiError } from '@/api/http'
import { onRoomEvent } from '@/mqtt/roomMqtt'
import { useTts } from '@/composables/useTts'
import { useNotificationSound } from '@/composables/useNotificationSound'
import type { RoomRent } from '@/types/game'

const { speak } = useTts()
const { playDing, playError } = useNotificationSound()

/**
 * AI 심판.
 *
 *   지원 게임 대여  -> 'prompt'  권유 팝업
 *   확인            -> 'active'  플로팅 패널 (턴 넘기기 / 이전 화면)
 *
 * 켜진 뒤에는 패널이 계속 떠 있다. 게임 목록을 가리지 않도록 접을 수 있고,
 * 접으면 작은 알약 형태로 남는다.
 *
 * 어떤 게임으로 시작할지도, 어느 세션에 턴을 넘길지도 **묻지 않는다** - 둘 다 서버가
 * 들고 있다. 태블릿의 rents 는 8초 폴링 스냅샷이고 sessionId 는 새로고침에 날아간다.
 */
export type RefereePhase = 'idle' | 'prompt' | 'active'

/** 루미큐브 타일 한 장. number 0 은 조커다. */
export interface Tile {
  color: string
  number: number
}

/** turn-log 이벤트가 온 것으로 칠 수 있는 페이로드인지 */
function isTurnLogPayload(payload: unknown): boolean {
  if (typeof payload !== 'object' || payload === null) return false
  return Array.isArray((payload as Record<string, unknown>).table)
}

/** 서버에 기록된 마지막 턴 ('이전 화면 보기' 가 그리는 값) */
export interface StoredTurnLog {
  turnNo: number
  tileCount: number
  table: Tile[][]
}

/** 진행자가 잡아낸 규칙 위반 */
export interface Violation {
  /** 고정 위반 코드 ('색깔 중복', '순서 오류', '타일 부족', …) */
  code: string
  /** 태블릿에 그대로 표시할 문구 */
  message: string
  /** 문제가 된 세트들. turn-log 의 table 과 같은 모양이다. 없으면 빈 배열. */
  table: Tile[][]
}

/** 세트 배열을 타일 배열로 정규화한다. 형태가 어긋난 세트/타일은 버린다. */
function toTable(raw: unknown): Tile[][] {
  if (!Array.isArray(raw)) return []

  return raw
    .filter((tileSet): tileSet is unknown[] => Array.isArray(tileSet))
    .map((tileSet) =>
      tileSet.reduce<Tile[]>((tiles, item) => {
        if (typeof item !== 'object' || item === null) return tiles
        const { color, number } = item as Record<string, unknown>
        const parsedNumber = Number(number)
        if (typeof color !== 'string' || Number.isNaN(parsedNumber)) return tiles
        tiles.push({ color, number: parsedNumber })
        return tiles
      }, []),
    )
}

/**
 * mc/event/violation 페이로드를 화면용으로 바꾼다.
 *
 * message 가 비어 오면 code 를 대신 보여준다 - 무엇이 잘못됐는지는 알려야 한다.
 * 둘 다 없으면 띄울 내용이 없으므로 버린다.
 *
 * table 은 문제가 된 세트(들)다 - turn-log 의 table 과 같은 필드명, 같은 모양으로 온다.
 */
function toViolation(payload: unknown): Violation | null {
  if (typeof payload !== 'object' || payload === null) return null

  const { code, message, table } = payload as Record<string, unknown>
  const parsedCode = typeof code === 'string' ? code : ''
  const parsedMessage = typeof message === 'string' ? message : ''
  if (!parsedCode && !parsedMessage) return null

  return {
    code: parsedCode,
    message: parsedMessage || parsedCode,
    table: toTable(table),
  }
}

/**
 * 타일 색. 루미큐브는 빨강·파랑·검정·주황 4색이고, 판본에 따라 주황을 노랑이라 부른다.
 *
 * 진행자가 보내는 값을 그대로 신뢰하지 않고 아는 색만 칠한다 - 모르는 색이 오면
 * 회색으로 두고 색 이름을 툴팁으로 남긴다. 어떤 표기로 올지 확정되지 않아
 * 영문/한글을 함께 받아 둔다.
 *
 * 색은 style.css 의 --color-tile-* 토큰이다. 하드코딩하면 다크 테마에서
 * 검정 타일이 어두운 배경에 묻힌다.
 */
const TILE_COLORS: Record<string, string> = {
  red: 'text-tile-red',
  빨강: 'text-tile-red',
  blue: 'text-tile-blue',
  파랑: 'text-tile-blue',
  black: 'text-tile-black',
  검정: 'text-tile-black',
  orange: 'text-tile-orange',
  주황: 'text-tile-orange',
  yellow: 'text-tile-orange',
  노랑: 'text-tile-orange',
}

/** 타일 배경/글자색 클래스. 모르는 색은 회색으로 둔다. */
export function tileColorClass(color: string): string {
  return TILE_COLORS[color.trim().toLowerCase()] ?? 'text-muted'
}

/** 조커는 0번이라 숫자 대신 표시한다 */
export function tileLabel(tile: Tile): string {
  return tile.number === 0 ? '조커' : String(tile.number)
}

/**
 * GET /mc/turn-log 응답을 화면용으로 바꾼다.
 *
 * 서버가 이미 파싱해서 내려주지만 타입만 믿지 않고 한 번 더 정규화한다 -
 * 손으로 넣은 행이 섞여 있어도 화면이 깨지지 않아야 한다.
 */
function toStoredTurnLog(raw: LatestTurnLog): StoredTurnLog {
  return {
    turnNo: Number(raw.turnNo) || 0,
    tileCount: Number(raw.tileCount) || 0,
    table: toTable(raw.table),
  }
}

/**
 * AI 심판이 진행할 수 있는 게임. 이름 비교인 이유는 서버에 지원 여부 컬럼이 없어서다.
 *
 * TODO(api): board_game 에 지원 플래그가 생기면 이 목록을 지우고 서버 값으로 판단한다.
 *   지금은 지원 게임이 늘 때마다 여기와 서버 양쪽을 고쳐야 한다.
 */
const SUPPORTED_GAMES = ['루미큐브', 'rummikub']

/**
 * 권유에 이미 답한 게임. 폴링이 8초마다 같은 목록을 물어오므로 이게 없으면 팝업이 계속 뜬다.
 *
 * **대여 건(rentId)이 아니라 게임 id 로 기억한다.** POST /rent 가 돌려주는 rentId 를
 * 믿을 수 없기 때문이다 - 서버 RentMapper.insert 는 방에 status='rent' 행이 이미 있으면
 * UPDATE 로 덮어쓰고 INSERT 는 건너뛰는데, 그 경로에서는 삽입된 행이 없어
 * useGeneratedKeys 가 rentId 를 채우지 못하고 null 로 내려온다. 그 null 을 '답한 대여'
 * 로 기억해 봐야 다음 폴링이 진짜 rentId 를 물어오는 순간 처음 보는 대여가 되어
 * 팝업이 다시 뜬다. boardGameId 는 POST /rent 와 GET /rent 양쪽에 항상 들어 있다.
 *
 * 반납돼서 대여 목록에서 빠지면 지운다(syncWithRents) - 다음에 다시 빌리면 새 판이라
 * 한 번 더 묻는 게 맞다. 모듈 스코프라 화면을 옮겨도 유지되고, 새로고침하면 비워진다.
 */
const answeredGameIds = new Set<number>()

const phase = ref<RefereePhase>('idle')
/** 서버에 세션을 물어봤는지. 이 전에는 권유 팝업을 띄우지 않는다. */
const isRestored = ref(false)
const target = ref<RoomRent | null>(null)
/**
 * 지금 방이 들고 있는 지원 게임. 권유에 답했는지와 무관하게 갱신한다.
 *
 * 한 번 끄고 나면 권유 팝업은 다시 뜨지 않으므로(같은 대여 건은 답한 것으로 남는다),
 * 이 값이 있어야 화면이 '다시 켜기' 진입점을 띄울 수 있다. 없으면 끄기가 편도가 된다.
 */
const supportedRent = ref<RoomRent | null>(null)
const boardGameName = ref('')
const isSubmitting = ref(false)
const isCollapsed = ref(false)

/**
 * 지금까지 기록된 턴 수.
 *
 * 브로커로 받은 개수를 세는 것이 아니라 서버가 매긴 turn_no 를 기준으로 삼는다 -
 * 세션 복원 때 서버 값으로 맞추고, 그 뒤 이벤트마다 하나씩 올린다.
 * 받은 개수만 세면 새로고침한 방이 3턴째인데 0 으로 보인다.
 */
const turnCount = ref(0)

/** '이전 화면 보기' 로 서버에서 읽어 온 마지막 턴 */
const latestTurn = ref<StoredTurnLog | null>(null)
const isTurnLoading = ref(false)
const turnLoadError = ref<string | null>(null)

/**
 * 지금 손님에게 보여줄 규칙 위반. 최신 한 건만 들고 있다.
 *
 * 위반은 '지금 테이블 상태' 에 대한 지적이라 쌓아 두면 이미 고친 지적까지 남는다.
 * 다음 턴을 넘기면(=수를 고쳤다는 뜻) 지운다.
 */
const violation = ref<Violation | null>(null)
const isHistoryOpen = ref(false)

/**
 * 좌석 상태. 원칙은 **서버가 준 값을 받아 적는다** - 화면에서 굴리지 않는다.
 *
 * 끝난 사람 건너뛰기 같은 규칙을 화면에도 두면 언젠가 서버와 어긋나고, 그러면
 * 진행자에게 가는 좌석과 화면에 보이는 좌석이 달라진다. 그 어긋남은 눈에 안 띄는데
 * 결과는 "3번이 두는데 2번의 첫 등록 여부로 판정" 이라 조용히 틀린 판정이 나온다.
 *
 * 예외가 하나 있다: 음성(wake/status finish)은 서버가 같은 이벤트를 받아 이미 턴을
 * 처리하므로 태블릿이 REST 를 부르면 한 수가 두 번 처리된다. 그래서 그 경로만
 * advanceSeatLocally() 로 화면의 좌석을 직접 돌린다. 다음 서버 응답(턴 넘기기 버튼,
 * '다 냈어요', 새로고침 복원)이 오면 그 값으로 덮어써서 어긋남이 오래 남지 않는다.
 */
const playerCount = ref(0)
const currentSeat = ref(0)
const finishedSeats = ref<number[]>([])

function isSupported(gameName: string): boolean {
  const normalized = gameName.trim().toLowerCase()
  return SUPPORTED_GAMES.some((name) => name.toLowerCase() === normalized)
}

/**
 * 분석 결과 도착. 턴 수는 이 이벤트를 센 값이다.
 *
 * 모듈 스코프에 한 번만 등록한다 - 컴포넌트가 몇 개 붙든 한 번만 쌓여야 한다.
 * 심판이 꺼져 있을 때 오는 이벤트는 버린다(지난 판의 뒤늦은 이벤트).
 */
onRoomEvent('mc/event/turn-log', (payload) => {
  if (phase.value !== 'active') return

  if (!isTurnLogPayload(payload)) {
    console.warn('[mc] turn-log 페이로드를 해석할 수 없다', payload)
    return
  }
  // 테이블 내용은 여기서 쓰지 않는다 - '이전 화면 보기' 는 DB 를 읽으므로,
  // 이 이벤트는 "한 턴이 더 기록됐다" 는 신호로만 쓴다.
  turnCount.value += 1
  playDing()
})

/**
 * 규칙 위반 도착.
 *
 * 접혀 있으면 펼친다 - 알약 뒤에 가려져 있으면 손님이 지적을 못 보고 그대로 진행한다.
 * 서버도 같은 이벤트를 받아 집계용으로 적재하지만, 화면 표시는 여기서만 한다.
 */
onRoomEvent('mc/event/violation', (payload) => {
  if (phase.value !== 'active') return

  const received = toViolation(payload)
  if (!received) {
    console.warn('[mc] violation 페이로드를 해석할 수 없다', payload)
    return
  }
  violation.value = received
  isCollapsed.value = false
  playError()
  speak(received.message)
})

/**
 * wake/status 페이로드에서 status 를 뽑는다.
 *
 * JSON 객체({status:'finish'})로도, 평문('finish')으로도 올라올 수 있다 -
 * roomMqtt 의 dispatch 는 JSON 이 아니면 문자열을 그대로 넘긴다.
 */
function toWakeStatus(payload: unknown): string {
  if (typeof payload === 'string') return payload.trim().toLowerCase()
  if (typeof payload !== 'object' || payload === null) return ''

  const { status } = payload as Record<string, unknown>
  return typeof status === 'string' ? status.trim().toLowerCase() : ''
}

/**
 * 화면의 좌석만 다음 사람에게 돌린다. 손패를 다 낸 좌석은 건너뛴다.
 *
 * 서버에 아무것도 묻지 않는다 - 서버는 이미 제 쪽에서 턴을 넘긴 상태다.
 * 한 바퀴 돌아 넘길 사람이 없으면(모두 끝났다) 그대로 둔다. 세션 종료는 서버가
 * 판단하는 일이라 여기서 패널을 닫지 않는다.
 */
function advanceSeatLocally(): void {
  const total = playerCount.value
  if (total < 1) return

  const finished = new Set(finishedSeats.value)
  for (let step = 1; step <= total; step += 1) {
    // currentSeat 이 0(복원 전)이면 1번부터 시작한다
    const seat = ((currentSeat.value - 1 + step) % total) + 1
    if (!finished.has(seat)) {
      currentSeat.value = seat
      return
    }
  }
}

/**
 * 음성으로 턴이 넘어갔다. status='finish' 는 "이 사람 수를 뒀다" 는 신호다.
 *
 * **REST 를 부르지 않는다.** 서버가 같은 wake/status 를 받아 분석과 좌석 회전을 이미
 * 하므로 태블릿까지 /mc/analyze 를 부르면 한 수가 두 번 처리된다. 여기서는 화면의
 * 좌석 표시만 따라가고, 턴 수는 서버가 올려 주는 mc/event/turn-log 가 센다.
 *
 * 심판이 꺼져 있을 때 오는 건 버린다(넘길 차례가 없다).
 * finish 외의 status(듣기 시작 등)는 이 화면에서 쓸 일이 없어 조용히 흘린다.
 */
onRoomEvent('wake/status', (payload) => {
  if (phase.value !== 'active') return
  if (toWakeStatus(payload) !== 'finish') return

  // 버튼으로 넘기는 중이면 건드리지 않는다. 그 응답이 서버 값으로 좌석을 정하는데,
  // 여기서 미리 돌려 두면 응답이 오기 전까지 엉뚱한 좌석이 보인다.
  if (isSubmitting.value) return

  // 지난 지적은 지운다 - 버튼으로 넘길 때와 같다. 여전히 문제가 있으면
  // 진행자가 새 violation 을 다시 올려 준다.
  violation.value = null
  advanceSeatLocally()
})

export function useAiReferee() {
  /**
   * 화면을 띄울 때 한 번 - 서버에 진행 중인 세션이 있으면 패널을 복원한다.
   *
   * 태블릿은 sessionId 를 보관하지 않는다. 새로고침에 잃고, localStorage 에 넣어도
   * 서버가 재배포되면 죽은 값을 들고 있게 되므로 서버가 유일한 근거다.
   *
   * 이 복원이 없으면 새로고침한 방에 권유 팝업이 다시 뜨고, 확인하면 판이 둘로 갈린다.
   * 실패해도 화면은 떠야 하므로 삼킨다 - 그 경우 심판이 꺼진 것으로 보인다.
   */
  async function restoreSession(): Promise<void> {
    try {
      const session = await fetchMcSession()
      if (session) {
        boardGameName.value = session.boardGameName
        turnCount.value = Number(session.turnNo) || 0
        // 좌석까지 복원해야 한다. 이게 없으면 새로고침한 화면이 "1번 차례" 로 돌아가는데
        // 서버는 계속 제 좌석으로 지시를 보내므로 손님만 엉뚱한 사람을 쳐다본다.
        playerCount.value = Number(session.playerCount) || 0
        currentSeat.value = Number(session.currentSeat) || 0
        finishedSeats.value = Array.isArray(session.finishedSeats) ? session.finishedSeats : []
        latestTurn.value = null
        violation.value = null
        isCollapsed.value = false
        isHistoryOpen.value = false
        phase.value = 'active'
      }
    } catch {
      // 무시 - 심판이 꺼진 상태로 시작한다
    } finally {
      isRestored.value = true
    }
  }

  /**
   * 대여 목록이 바뀔 때마다 호출한다. 지원 게임이 새로 들어와 있으면 권유 팝업을 연다.
   *
   * 대여 상태(RENT/USING)는 가리지 않는다. 카드를 태그해 꺼내야 USING 이 되는데,
   * 그때까지 기다리면 손님이 게임을 펼친 뒤에야 권유가 뜬다.
   */
  function syncWithRents(rents: RoomRent[]): void {
    supportedRent.value = rents.find((rent) => isSupported(rent.gameName)) ?? null

    // 반납해서 목록에서 빠진 게임의 답은 잊는다. 다시 빌리면 새 판이라 다시 물어야 한다.
    // (조회에 실패하면 useRoomRents 가 예전 목록을 그대로 두므로 여기서 잘못 지워지지 않는다)
    for (const gameId of answeredGameIds) {
      if (!rents.some((rent) => rent.gameId === gameId)) {
        answeredGameIds.delete(gameId)
      }
    }

    // 복원을 마치기 전에는 권유하지 않는다. 대여 목록이 세션 조회보다 먼저 도착하면
    // 이미 심판이 도는 방에 "켤까요?" 를 띄우게 된다.
    if (!isRestored.value) return
    if (phase.value !== 'idle' || isSubmitting.value) return

    const candidate = supportedRent.value
    if (!candidate || answeredGameIds.has(candidate.gameId)) return

    target.value = candidate
    phase.value = 'prompt'
  }

  /** 나중에 하기 / 바깥 클릭. 그 게임을 반납할 때까지는 다시 묻지 않는다. */
  function dismiss(): void {
    if (target.value) answeredGameIds.add(target.value.gameId)
    target.value = null
    phase.value = 'idle'
  }

  /**
   * 확인 -> AI 심판 시작.
   *
   * 실패해도 답한 것으로 처리한다. 서버가 거절한 상황에서 팝업이 8초마다 다시 뜨면
   * 화면을 쓸 수 없다. 다시 켜려면 게임을 다시 대여하면 된다.
   *
   * @param count 팝업에서 고른 인원. 서버가 게임의 인원 범위로 한 번 더 검증한다.
   * @throws ApiError 서버가 거절한 경우. 화면이 문구를 정한다.
   */
  async function confirm(count: number): Promise<string> {
    const gameId = target.value?.gameId ?? null
    isSubmitting.value = true

    try {
      const started = await startMc(count)
      boardGameName.value = started.boardGameName
      // 요청한 count 가 아니라 응답 값을 쓴다 - 이미 켜져 있던 세션이면 서버가
      // 요청을 무시하고 진행 중인 판의 인원을 돌려준다.
      playerCount.value = Number(started.playerCount) || count
      currentSeat.value = Number(started.currentSeat) || 1
      finishedSeats.value = []
      turnCount.value = 0
      latestTurn.value = null
      violation.value = null
      isCollapsed.value = false
      isHistoryOpen.value = false
      phase.value = 'active'
      return started.boardGameName
    } catch (error) {
      phase.value = 'idle'
      throw error
    } finally {
      isSubmitting.value = false
      if (gameId !== null) answeredGameIds.add(gameId)
      target.value = null
    }
  }

  /**
   * 껐다가 다시 켜기 -> 권유 팝업을 다시 연다.
   *
   * 바로 시작하지 않는 이유는 인원을 물어봐야 하기 때문이다. 지난번 값을 재사용하면
   * 사람이 빠지거나 늘어난 채로 판이 시작되고, 좌석 수가 틀리면 진행자의 첫 등록
   * 판정이 통째로 엉뚱한 사람에게 붙는다. 인원을 묻는 UI 를 두 군데 두지 않으려고
   * 팝업 하나로 모은다.
   *
   * 답한 게임이라 syncWithRents 는 팝업을 다시 띄우지 않으므로 여기서 직접 연다.
   */
  function restart(): void {
    if (!supportedRent.value) return
    target.value = supportedRent.value
    phase.value = 'prompt'
  }

  /**
   * 서버가 돌려준 좌석 회전 결과를 화면에 반영한다.
   *
   * sessionEnded 면 서버 세션은 이미 없다 - 패널을 닫아야 한다. 남겨 두면 다음
   * 턴 넘기기가 MC_SESSION_NOT_FOUND 로 떨어진다.
   */
  function applyTurn(result: McTurnResult): void {
    if (result.sessionEnded) {
      resetSessionState()
      return
    }
    currentSeat.value = Number(result.currentSeat) || 0
  }

  /** 패널을 닫고 세션에 딸린 화면 상태를 모두 비운다 */
  function resetSessionState(): void {
    phase.value = 'idle'
    turnCount.value = 0
    latestTurn.value = null
    violation.value = null
    isHistoryOpen.value = false
    isCollapsed.value = false
    boardGameName.value = ''
    playerCount.value = 0
    currentSeat.value = 0
    finishedSeats.value = []
  }

  /**
   * '다 냈어요' - 지금 차례인 사람이 손패를 비웠다.
   *
   * 카메라는 손패를 못 보니 사람이 눌러 줘야 한다. 서버가 그 좌석을 차례에서 빼고,
   * 마지막 한 명만 남으면 세션까지 끝낸다.
   *
   * @returns 세션이 끝났으면 true (화면이 안내 문구를 다르게 낸다)
   * @throws ApiError 진행 중인 세션이 없는 경우 등
   */
  async function finishCurrentPlayer(): Promise<boolean> {
    isSubmitting.value = true
    try {
      const result = await finishPlayerMc()
      // 끝난 좌석은 서버 응답의 seat 이다. 화면의 currentSeat 을 쓰면 그 사이
      // 다른 경로로 차례가 넘어갔을 때 엉뚱한 좌석에 완료 표시가 붙는다.
      finishedSeats.value = [...finishedSeats.value, result.seat]
      applyTurn(result)
      return result.sessionEnded
    } finally {
      isSubmitting.value = false
    }
  }

  /**
   * 심판 끄기.
   *
   * 서버가 거절해도 패널은 닫는다. 손님이 끄겠다고 눌렀는데 화면에 남아 있으면
   * 다시 누를 수밖에 없고, 서버 쪽 세션은 이미 없는 경우가 대부분이다.
   *
   * @throws ApiError 서버가 거절한 경우. 상태는 이미 정리된 뒤다.
   */
  async function stop(): Promise<void> {
    isSubmitting.value = true
    try {
      await finishMc()
    } finally {
      isSubmitting.value = false
      resetSessionState()
    }
  }

  /**
   * '이전 화면 보기' - 서버에 기록된 마지막 턴을 읽어 모달을 연다.
   *
   * 모달을 먼저 띄우고 그 안에서 로딩을 보여준다. 응답을 기다렸다 열면 버튼을 눌렀는데
   * 아무 반응이 없는 구간이 생긴다.
   */
  async function openHistory(): Promise<void> {
    isHistoryOpen.value = true
    isTurnLoading.value = true
    turnLoadError.value = null

    try {
      const stored = await fetchLatestTurnLog()
      latestTurn.value = stored ? toStoredTurnLog(stored) : null
    } catch (error) {
      latestTurn.value = null
      turnLoadError.value = isApiError(error)
        ? error.message
        : '테이블 상태를 불러오지 못했습니다.'
    } finally {
      isTurnLoading.value = false
    }
  }

  /**
   * 턴 넘기기 -> 분석 지시.
   *
   * 결과는 mc/event/turn-log 로 따로 올라오므로 여기서는 기다리지 않는다.
   *
   * @throws ApiError 진행 중인 세션이 없는 경우 등
   */
  async function passTurn(): Promise<void> {
    isSubmitting.value = true
    // 지난 지적은 지운다. 턴을 넘긴다는 건 그 수를 마쳤다는 뜻이라,
    // 여전히 문제가 있으면 진행자가 새 violation 을 다시 올려 준다.
    violation.value = null
    try {
      applyTurn(await analyzeMc())
    } finally {
      isSubmitting.value = false
    }
  }

  return {
    phase: computed(() => phase.value),
    isPrompting: computed(() => phase.value === 'prompt'),
    isActive: computed(() => phase.value === 'active'),
    /** 권유 팝업에 띄울 게임명 (대여 목록 기준) */
    promptGameName: computed(() => target.value?.gameName ?? ''),
    /** 권유 팝업이 가리키는 게임. 인원 선택 범위를 목록에서 찾는 데 쓴다. */
    promptGameId: computed(() => target.value?.gameId ?? null),
    /** 패널에 띄울 게임명 (서버가 고른 값) */
    boardGameName: computed(() => boardGameName.value),
    turnCount: computed(() => turnCount.value),
    playerCount: computed(() => playerCount.value),
    currentSeat: computed(() => currentSeat.value),
    finishedSeats: computed(() => finishedSeats.value),
    /** 아직 손패를 다 내지 않은 인원 */
    remainingPlayers: computed(() => playerCount.value - finishedSeats.value.length),
    /** 지금 보여줄 규칙 위반 (없으면 null) */
    violation: computed(() => violation.value),
    dismissViolation: () => (violation.value = null),
    /** '이전 화면 보기' 가 그리는 값 (서버에 기록된 마지막 턴) */
    latestTurn: computed(() => latestTurn.value),
    isTurnLoading: computed(() => isTurnLoading.value),
    turnLoadError: computed(() => turnLoadError.value),
    isSubmitting: computed(() => isSubmitting.value),
    isCollapsed: computed(() => isCollapsed.value),
    isHistoryOpen: computed(() => isHistoryOpen.value),
    /** 꺼져 있지만 지원 게임을 들고 있어 다시 켤 수 있는 상태 */
    canStart: computed(() => phase.value === 'idle' && supportedRent.value !== null),
    toggleCollapsed: () => (isCollapsed.value = !isCollapsed.value),
    openHistory,
    closeHistory: () => (isHistoryOpen.value = false),
    restoreSession,
    syncWithRents,
    dismiss,
    confirm,
    restart,
    passTurn,
    finishCurrentPlayer,
    stop,
  }
}
