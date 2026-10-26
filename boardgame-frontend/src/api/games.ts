import { ROOM_NUMBER } from '@/config/env'
import type {
  BoardGame,
  BoardGameDetail,
  Reservation,
  RoomRent,
} from '@/types/game'
import type {
  ActiveRentDto,
  BoardGameDetailDto,
  BoardGameListDto,
  RentDto,
  ReservationDto,
  RoomUsageDto,
} from './dto'
import {
  toBoardGame,
  toBoardGameDetail,
  toCreatedRent,
  toReservation,
  toRoomRent,
  toRoomStartedAt,
} from './mappers'
import { request } from './http'

/**
 * 보드게임 조회 / 대여 / 예약 API.
 *
 * 서버에는 인증이 없고 roomNumber 가 곧 신원이다. 그 값을 이 파일이 직접
 * 주입하므로 화면/컴포저블은 roomNumber 를 몰라도 된다 — 나중에 기기
 * 프로비저닝으로 바뀌어도 src/config/env.ts 만 고치면 된다.
 */

/**
 * 전체 목록 또는 이름 검색.
 *
 * 서버는 keyword / categoryId / players 필터를 지원하지만 화면 필터링은
 * 전부 클라이언트에서 한다 — 검색어를 지울 때 재요청이 없어 태블릿에서 즉각적이고,
 * 상황별 칩('처음이에요' / '30분 안에' / '지금 가능')은 서버 파라미터가 없다.
 * keyword 인자는 서버 검색이 필요해질 때를 위해 남겨둔다.
 */
export async function fetchGames(keyword?: string): Promise<BoardGame[]> {
  const games = await request<BoardGameListDto[]>('/boardgame', {
    query: { keyword },
  })
  return games.map(toBoardGame)
}

/** 존재하지 않으면 404 BOARD_GAME_NOT_FOUND 로 throw 한다 */
export async function fetchGame(id: number): Promise<BoardGameDetail> {
  const game = await request<BoardGameDetailDto>(`/boardgame/${id}`)
  return toBoardGameDetail(game)
}

/**
 * 대여. 사본 하나를 RENTED 로 잡고 rent 행을 status='RENT' 로 만든다.
 *
 * **사물함은 여기서 열리지 않는다.** MQTT 발행은 카드 태그(RentService.openCabinetByCard)
 * 에서만 일어난다 — 이 응답의 cabinetId 는 '태그하면 열릴 사물함' 이다.
 *
 * 실패 코드: BOARD_GAME_OUT_OF_STOCK, ALREADY_RENTED(우리 방이 이미 들고 있다),
 *           ROOM_NOT_IN_USE, ROOM_NOT_FOUND, BOARD_GAME_NOT_FOUND
 */
export async function rentGame(gameId: number): Promise<RoomRent> {
  const rent = await request<RentDto>('/rent', {
    method: 'POST',
    body: { boardGameId: gameId, roomNumber: ROOM_NUMBER },
  })
  return toCreatedRent(rent)
}

/**
 * 우리 방이 아직 반납하지 않은 대여 목록.
 *
 * 새로고침 후에도 '사용 중 / 꺼내기 대기' 를 복원하는 유일한 수단이다. 픽업·반납은
 * 카드 태그로 서버에서만 전이되므로 대여 응답을 들고 있는 것으로는 알 수 없다.
 */
export async function fetchActiveRents(): Promise<RoomRent[]> {
  const rents = await request<ActiveRentDto[]>('/rent', {
    query: { roomNumber: ROOM_NUMBER },
  })
  return rents.map(toRoomRent)
}

/**
 * 대기열 등록. 재고가 남아 있으면 서버가 RESERVATION_NOT_NEEDED 로 거절한다
 * (그때는 예약이 아니라 대여를 해야 한다).
 *
 * 실패 코드: RESERVATION_NOT_NEEDED, DUPLICATE_RESERVATION(방당 1건),
 *           ALREADY_RENTED, ROOM_NOT_IN_USE
 */
export async function createReservation(gameId: number): Promise<Reservation> {
  const reservation = await request<ReservationDto>('/reservation', {
    method: 'POST',
    body: { boardGameId: gameId, roomNumber: ROOM_NUMBER },
  })
  return toReservation(reservation)
}

/**
 * 예약 취소(soft delete). DELETE 가 아니라 PATCH 이고, roomNumber 가
 * 소유 증명 역할을 한다(불일치 시 403 RESERVATION_FORBIDDEN).
 */
export async function cancelReservation(
  reservationId: number,
): Promise<Reservation> {
  const reservation = await request<ReservationDto>('/reservation/cancel', {
    method: 'PATCH',
    body: { roomNumber: ROOM_NUMBER, reservationId },
  })
  return toReservation(reservation)
}

/**
 * 이 방의 진행 중인 예약. 서버가 방당 WAITING 1건을 유니크 제약으로
 * 보장하므로 첫 건만 취한다. 태블릿을 새로고침해도 예약 배너를 복원하는 데 쓴다.
 */
export async function fetchWaitingReservation(): Promise<Reservation | null> {
  const reservations = await request<ReservationDto[]>('/reservation', {
    query: { roomNumber: ROOM_NUMBER, status: 'WAITING' },
  })
  const waiting = reservations[0]
  return waiting ? toReservation(waiting) : null
}

/*
 * 예약 알림('지금 대여' / '예약 취소')에는 전용 엔드포인트가 없다. 위의 rentGame /
 * cancelReservation 을 그대로 쓴다 — 서버 RentService.rent 가 대여와 같은 트랜잭션에서
 * 그 방의 WAITING 예약을 FULFILLED 로 넘겨 주므로 예약을 따로 정리할 필요가 없다.
 */

/**
 * 헤더 이용 시간 표시용. room_usage 에서 이 방의 가장 최근 건(start_time 기준)을
 * 찾아 입실 시각을 돌려준다. 이용 이력이 없으면 null — 그때 화면은 태블릿 가동
 * 시간을 대신 세지 않고 00:00:00 으로 둔다(추측한 시각을 보여주지 않기 위함).
 */
export async function fetchRoomStartedAt(): Promise<number | null> {
  const usage = await request<RoomUsageDto>('/admin/room/usage', {
    query: { roomNumber: ROOM_NUMBER },
  })
  return toRoomStartedAt(usage)
}
