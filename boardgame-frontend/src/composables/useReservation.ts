import { computed, ref } from 'vue'
import type {
  BoardGame,
  Reservation,
  ReservationAlert,
  RoomRent,
} from '@/types/game'
import {
  cancelReservation,
  createReservation,
  fetchWaitingReservation,
  rentGame,
} from '@/api/games'
import { isApiError } from '@/api/http'
import { onRoomEvent } from '@/mqtt/roomMqtt'

/**
 * 예약 상태 관리.
 *
 * 반납 알림은 브로커에서 직접 받는다:
 *
 *   다른 방이 반납 -> 서버가 대기 1번인 방에게만 발행
 *   -> /room/{room}/reservation/ready -> 팝업 + 카운트다운
 *   -> '지금 대여'  POST /rent            (서버가 예약도 FULFILLED 로 넘긴다)
 *   -> '예약 취소'  PATCH /reservation/cancel (서버가 바로 다음 대기자에게 넘긴다)
 *   -> 무응답      서버가 timeoutSec 뒤 예약을 취소하고 다음 대기자에게 넘긴다
 *
 * 참고: inte-server ReservationNotifyService.
 */

/**
 * 서버가 timeoutSec 을 안 실어 보냈을 때 쓸 값.
 * inte-server 의 reservation.popup-timeout-sec 기본값과 같게 맞춰 둔다.
 */
const FALLBACK_TIMEOUT_SECONDS = 60

/** 한 방에는 예약이 최대 1건 (서버도 유니크 제약으로 보장) */
const reservation = ref<Reservation | null>(null)
const isSubmitting = ref(false)

/** 반납되어 대여 가능해졌을 때 뜨는 알림 */
const returnAlert = ref<ReservationAlert | null>(null)
const remainingSeconds = ref(0)
/** 무응답으로 시간이 다 된 알림의 게임 이름. 화면이 감시하다 토스트로 띄운다. */
const expiredGameName = ref<string | null>(null)

let countdownId: ReturnType<typeof setInterval> | null = null

function stopCountdown(): void {
  if (countdownId) {
    clearInterval(countdownId)
    countdownId = null
  }
}

function closeAlert(): void {
  stopCountdown()
  returnAlert.value = null
  remainingSeconds.value = 0
}

/**
 * `/room/{roomNumber}/reservation/ready` 페이로드를 화면용으로 바꾼다.
 *
 * 브로커에서 바로 받는 값이라 스키마를 신뢰할 수 없다. 어느 예약인지(reservationId)와
 * 무엇을 빌릴지(boardGameId) 를 모르면 두 버튼 다 만들 수 없으므로 그때만 버린다.
 */
function toReservationAlert(payload: unknown): ReservationAlert | null {
  if (typeof payload !== 'object' || payload === null) return null

  const { reservationId, boardGameId, boardGameName, timeoutSec } =
    payload as Record<string, unknown>
  if (typeof reservationId !== 'number' || typeof boardGameId !== 'number') {
    return null
  }

  return {
    reservationId,
    gameId: boardGameId,
    gameName:
      typeof boardGameName === 'string' && boardGameName
        ? boardGameName
        : '예약한 게임',
    timeoutSec:
      typeof timeoutSec === 'number' && timeoutSec > 0
        ? timeoutSec
        : FALLBACK_TIMEOUT_SECONDS,
  }
}

/**
 * 팝업 열기 + 카운트다운 시작.
 *
 * 화면 타이머는 서버 타이머를 비추기만 한다 — 실제 예약 취소는 서버가 한다.
 * 발행부터 수신까지의 지연 때문에 화면이 항상 서버보다 조금 늦게 끝나는데,
 * 그 틈에 누른 '지금 대여' 는 그대로 성공한다(대여는 예약 상태와 무관하다).
 */
function openAlert(next: ReservationAlert): void {
  stopCountdown()
  returnAlert.value = next
  remainingSeconds.value = next.timeoutSec

  countdownId = setInterval(() => {
    remainingSeconds.value -= 1
    if (remainingSeconds.value > 0) return

    // 서버가 이 시점에 예약을 취소하고 다음 대기자에게 넘긴다. 배너도 같이 비운다.
    expiredGameName.value = next.gameName
    reservation.value = null
    closeAlert()
  }, 1000)
}

/**
 * 반납 알림 수신.
 *
 * 모듈 스코프에 한 번만 등록한다 — 화면이 몇 개 붙든 팝업은 한 번만 떠야 한다.
 * 목록 화면이든 상세 화면이든 같은 상태를 보고 그리므로 어디에 있어도 알림을 놓치지 않는다.
 */
onRoomEvent('reservation/ready', (payload) => {
  const received = toReservationAlert(payload)
  if (!received) {
    console.warn('[reservation] ready 페이로드를 해석할 수 없다', payload)
    return
  }
  openAlert(received)
})

export function useReservation() {
  async function reserve(game: BoardGame): Promise<Reservation> {
    isSubmitting.value = true
    try {
      const created = await createReservation(game.id)
      reservation.value = created
      return created
    } finally {
      isSubmitting.value = false
    }
  }

  async function cancel(): Promise<void> {
    const current = reservation.value
    if (!current) return

    isSubmitting.value = true
    try {
      await cancelReservation(current.id)
      reservation.value = null
      if (returnAlert.value?.reservationId === current.id) closeAlert()
    } finally {
      isSubmitting.value = false
    }
  }

  /**
   * 서버에 남아 있는 이 방의 예약을 되살린다.
   * 태블릿을 새로고침하거나 키오스크가 재시작해도 예약 배너가 유지된다.
   * 실패는 조용히 무시한다 — 복원 실패로 목록 화면을 망칠 이유가 없다.
   *
   * 팝업은 복원하지 않는다. 서버가 응답을 기다리는 시간이 1분뿐이라 되살릴 가치가 없고,
   * 그동안 예약은 WAITING 으로 남아 다음 반납 때 정상적으로 다시 알림이 온다.
   */
  async function restore(): Promise<void> {
    try {
      reservation.value = await fetchWaitingReservation()
    } catch {
      // 무시
    }
  }

  /** 예약을 로컬에서만 비운다 (서버가 이미 취소/소멸시킨 경우) */
  function clearLocal(): void {
    reservation.value = null
    closeAlert()
  }

  /**
   * 알림에서 '지금 대여'. 평범한 대여와 같은 요청이다 —
   * 서버가 대여와 같은 트랜잭션에서 이 방의 예약을 FULFILLED 로 넘긴다.
   *
   * 요청을 보내기 전에 팝업부터 닫는다. 응답을 기다리는 사이 카운트다운이 0이 되면
   * 예약이 이미 끝난 것처럼 배너가 비워져 화면이 어긋난다.
   *
   * @throws ApiError 서버가 거절한 경우(BOARD_GAME_OUT_OF_STOCK 등). 화면이 문구를 정한다.
   */
  async function acceptAlert(): Promise<RoomRent | null> {
    const current = returnAlert.value
    if (!current) return null

    closeAlert()
    isSubmitting.value = true
    try {
      const created = await rentGame(current.gameId)
      reservation.value = null
      return created
    } finally {
      isSubmitting.value = false
    }
  }

  /**
   * 알림에서 '예약 취소'. 서버가 취소를 받는 즉시 다음 대기자에게 알림을 넘긴다.
   *
   * 이미 취소된 예약이라는 응답은 삼킨다 — 서버 타임아웃이 한발 먼저 취소한 경우인데,
   * 손님이 원한 결과와 같아서 실패로 보여줄 이유가 없다.
   */
  async function dismissAlert(): Promise<void> {
    const current = returnAlert.value
    if (!current) return

    closeAlert()
    isSubmitting.value = true
    try {
      await cancelReservation(current.reservationId)
    } catch (error) {
      if (
        !isApiError(error) ||
        !error.is('RESERVATION_NOT_CANCELABLE', 'RESERVATION_NOT_FOUND')
      ) {
        throw error
      }
    } finally {
      reservation.value = null
      isSubmitting.value = false
    }
  }

  /** 화면이 토스트로 띄운 뒤 호출한다 */
  function clearExpired(): void {
    expiredGameName.value = null
  }

  function isReserved(gameId: number): boolean {
    return reservation.value?.gameId === gameId
  }

  return {
    reservation,
    isSubmitting: computed(() => isSubmitting.value),
    returnAlert: computed(() => returnAlert.value),
    remainingSeconds: computed(() => remainingSeconds.value),
    alertProgress: computed(() =>
      returnAlert.value
        ? (remainingSeconds.value / returnAlert.value.timeoutSec) * 100
        : 0,
    ),
    expiredGameName: computed(() => expiredGameName.value),
    reserve,
    cancel,
    restore,
    clearLocal,
    acceptAlert,
    dismissAlert,
    clearExpired,
    isReserved,
  }
}
