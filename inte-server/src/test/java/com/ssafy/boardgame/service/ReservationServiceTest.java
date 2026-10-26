package com.ssafy.boardgame.service;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.dto.ReservationCancelRequest;
import com.ssafy.boardgame.dto.ReservationRequest;
import com.ssafy.boardgame.dto.ReservationResponse;
import com.ssafy.boardgame.dto.RoomResponse;
import com.ssafy.boardgame.mapper.BoardGameItemMapper;
import com.ssafy.boardgame.mapper.BoardGameMapper;
import com.ssafy.boardgame.mapper.RentMapper;
import com.ssafy.boardgame.mapper.ReservationMapper;
import com.ssafy.boardgame.mapper.RoomMapper;
import com.ssafy.boardgame.util.StatusUtil;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.BDDMockito.willAnswer;
import static org.mockito.Mockito.never;

@ExtendWith(MockitoExtension.class)
@DisplayName("ReservationService - 예약")
class ReservationServiceTest {

    private static final Long GAME_ID = 1L;
    private static final String GAME_NAME = "루미큐브";
    private static final String ROOM = "A1";
    private static final Long RESERVATION_ID = 77L;

    @Mock private BoardGameMapper boardGameMapper;
    @Mock private BoardGameItemMapper boardGameItemMapper;
    @Mock private ReservationMapper reservationMapper;
    @Mock private RentMapper rentMapper;
    @Mock private RoomMapper roomMapper;
    @Mock private ReservationNotifyService reservationNotifyService;

    @InjectMocks private ReservationService reservationService;

    private static ReservationRequest request() {
        ReservationRequest request = new ReservationRequest();
        request.setBoardGameId(GAME_ID);
        request.setRoomNumber(ROOM);
        return request;
    }

    private static RoomResponse room(String status) {
        RoomResponse room = new RoomResponse();
        room.setRoomNumber(ROOM);
        room.setCapacity(6);
        room.setStatus(status);
        return room;
    }

    private static ReservationResponse reservation(Long id, String roomNumber, String status) {
        ReservationResponse reservation = new ReservationResponse();
        reservation.setReservationId(id);
        reservation.setBoardGameId(GAME_ID);
        reservation.setRoomNumber(roomNumber);
        reservation.setStatus(status);
        return reservation;
    }

    @Nested
    @DisplayName("예약하기")
    class Reserve {

        /** 예약이 성립하는 조건: 방은 사용 중, 대여 이력 없음, 재고 0, 대기 예약 없음 */
        private void givenReservable() {
            given(boardGameMapper.findNameById(GAME_ID)).willReturn(GAME_NAME);
            given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(StatusUtil.STATUS_ROOM_USE));
            given(rentMapper.countActiveRent(ROOM, GAME_ID)).willReturn(0);
            given(boardGameItemMapper.countAvailable(GAME_ID)).willReturn(0);
            given(reservationMapper.findByRoom(ROOM, StatusUtil.STATUS_RESERVATION_WAITING))
                    .willReturn(List.of());
        }

        @Test
        @DisplayName("성공하면 대기 순번은 '앞선 대기 수 + 1' 이다")
        void reserve_success_computesWaitingRank() {
            givenReservable();
            // MyBatis useGeneratedKeys 가 파라미터 객체에 PK 를 채워 주는 동작을 흉내낸다.
            willAnswer(invocation -> {
                invocation.getArgument(0, ReservationResponse.class)
                        .setReservationId(RESERVATION_ID);
                return 1;
            }).given(reservationMapper).insert(any(ReservationResponse.class));
            given(reservationMapper.countWaitingAhead(RESERVATION_ID, GAME_ID)).willReturn(2);

            ReservationResponse response = reservationService.reserve(request());

            assertThat(response.getReservationId()).isEqualTo(RESERVATION_ID);
            assertThat(response.getBoardGameId()).isEqualTo(GAME_ID);
            assertThat(response.getBoardGameName()).isEqualTo(GAME_NAME);
            assertThat(response.getRoomNumber()).isEqualTo(ROOM);
            assertThat(response.getWaitingRank()).isEqualTo(3);
        }

        @Test
        @DisplayName("앞선 대기가 없으면 순번은 1 이다")
        void reserve_firstInLine_rankIsOne() {
            givenReservable();
            willAnswer(invocation -> {
                invocation.getArgument(0, ReservationResponse.class)
                        .setReservationId(RESERVATION_ID);
                return 1;
            }).given(reservationMapper).insert(any(ReservationResponse.class));
            given(reservationMapper.countWaitingAhead(RESERVATION_ID, GAME_ID)).willReturn(0);

            assertThat(reservationService.reserve(request()).getWaitingRank()).isEqualTo(1);
        }

        @Test
        @DisplayName("존재하지 않는 보드게임이면 BOARD_GAME_NOT_FOUND")
        void reserve_unknownBoardGame_throwsBoardGameNotFound() {
            given(boardGameMapper.findNameById(GAME_ID)).willReturn(null);

            assertThatThrownBy(() -> reservationService.reserve(request()))
                    .isInstanceOf(BusinessException.class)
                    .extracting(e -> ((BusinessException) e).getErrorCode())
                    .isEqualTo(ErrorCode.BOARD_GAME_NOT_FOUND);
        }

        @Test
        @DisplayName("존재하지 않는 방이면 ROOM_NOT_FOUND")
        void reserve_unknownRoom_throwsRoomNotFound() {
            given(boardGameMapper.findNameById(GAME_ID)).willReturn(GAME_NAME);
            given(roomMapper.findByRoomNumber(ROOM)).willReturn(null);

            assertThatThrownBy(() -> reservationService.reserve(request()))
                    .isInstanceOf(BusinessException.class)
                    .extracting(e -> ((BusinessException) e).getErrorCode())
                    .isEqualTo(ErrorCode.ROOM_NOT_FOUND);
        }

        @Test
        @DisplayName("방이 사용 중이 아니면 ROOM_NOT_IN_USE")
        void reserve_roomNotInUse_throwsRoomNotInUse() {
            given(boardGameMapper.findNameById(GAME_ID)).willReturn(GAME_NAME);
            given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(StatusUtil.STATUS_ROOM_EMPTY));

            assertThatThrownBy(() -> reservationService.reserve(request()))
                    .isInstanceOf(BusinessException.class)
                    .extracting(e -> ((BusinessException) e).getErrorCode())
                    .isEqualTo(ErrorCode.ROOM_NOT_IN_USE);
        }

        @Test
        @DisplayName("이미 그 게임을 대여 중이면 ALREADY_RENTED")
        void reserve_alreadyRented_throwsAlreadyRented() {
            given(boardGameMapper.findNameById(GAME_ID)).willReturn(GAME_NAME);
            given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(StatusUtil.STATUS_ROOM_USE));
            given(rentMapper.countActiveRent(ROOM, GAME_ID)).willReturn(1);

            assertThatThrownBy(() -> reservationService.reserve(request()))
                    .isInstanceOf(BusinessException.class)
                    .extracting(e -> ((BusinessException) e).getErrorCode())
                    .isEqualTo(ErrorCode.ALREADY_RENTED);
        }

        @Test
        @DisplayName("재고가 남아 있으면 예약할 이유가 없으므로 RESERVATION_NOT_NEEDED")
        void reserve_stockAvailable_throwsReservationNotNeeded() {
            given(boardGameMapper.findNameById(GAME_ID)).willReturn(GAME_NAME);
            given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(StatusUtil.STATUS_ROOM_USE));
            given(rentMapper.countActiveRent(ROOM, GAME_ID)).willReturn(0);
            given(boardGameItemMapper.countAvailable(GAME_ID)).willReturn(2);

            assertThatThrownBy(() -> reservationService.reserve(request()))
                    .isInstanceOf(BusinessException.class)
                    .extracting(e -> ((BusinessException) e).getErrorCode())
                    .isEqualTo(ErrorCode.RESERVATION_NOT_NEEDED);

            then(reservationMapper).should(never()).insert(any(ReservationResponse.class));
        }

        @Test
        @DisplayName("그 방에 대기 예약이 이미 있으면 DUPLICATE_RESERVATION")
        void reserve_roomAlreadyWaiting_throwsDuplicateReservation() {
            given(boardGameMapper.findNameById(GAME_ID)).willReturn(GAME_NAME);
            given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(StatusUtil.STATUS_ROOM_USE));
            given(rentMapper.countActiveRent(ROOM, GAME_ID)).willReturn(0);
            given(boardGameItemMapper.countAvailable(GAME_ID)).willReturn(0);
            given(reservationMapper.findByRoom(ROOM, StatusUtil.STATUS_RESERVATION_WAITING))
                    .willReturn(List.of(reservation(9L, ROOM, StatusUtil.STATUS_RESERVATION_WAITING)));

            assertThatThrownBy(() -> reservationService.reserve(request()))
                    .isInstanceOf(BusinessException.class)
                    .extracting(e -> ((BusinessException) e).getErrorCode())
                    .isEqualTo(ErrorCode.DUPLICATE_RESERVATION);
        }

        @Test
        @DisplayName("[정책] 방당 대기 1건 - 다른 게임을 대기 중이어도 새 예약은 막힌다")
        void reserve_waitingForDifferentGame_alsoBlocked() {
            given(boardGameMapper.findNameById(GAME_ID)).willReturn(GAME_NAME);
            given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(StatusUtil.STATUS_ROOM_USE));
            given(rentMapper.countActiveRent(ROOM, GAME_ID)).willReturn(0);
            given(boardGameItemMapper.countAvailable(GAME_ID)).willReturn(0);

            // 예약 대상은 보드게임이지만, 한 방이 동시에 걸 수 있는 대기는 1건이다.
            // 대기 중인 예약이 '다른 보드게임(99)' 이어도 거절된다.
            // DB 의 uq_reservation_waiting_room (room_number) 부분 유니크 인덱스가 같은 규칙을 보장한다.
            ReservationResponse otherGame = reservation(9L, ROOM, StatusUtil.STATUS_RESERVATION_WAITING);
            otherGame.setBoardGameId(99L);
            given(reservationMapper.findByRoom(ROOM, StatusUtil.STATUS_RESERVATION_WAITING))
                    .willReturn(List.of(otherGame));

            assertThatThrownBy(() -> reservationService.reserve(request()))
                    .isInstanceOf(BusinessException.class)
                    .extracting(e -> ((BusinessException) e).getErrorCode())
                    .isEqualTo(ErrorCode.DUPLICATE_RESERVATION);
        }
    }

    @Nested
    @DisplayName("예약 취소")
    class Cancel {

        private static ReservationCancelRequest cancelRequest(Long reservationId, String roomNumber) {
            ReservationCancelRequest request = new ReservationCancelRequest();
            request.setReservationId(reservationId);
            request.setRoomNumber(roomNumber);
            return request;
        }

        @Test
        @DisplayName("성공하면 CANCELLED 로 바뀐 예약을 다시 조회해 반환한다")
        void cancel_success_returnsReloadedReservation() {
            given(reservationMapper.findById(RESERVATION_ID))
                    .willReturn(reservation(RESERVATION_ID, ROOM, StatusUtil.STATUS_RESERVATION_WAITING),
                                reservation(RESERVATION_ID, ROOM, StatusUtil.STATUS_RESERVATION_CANCELLED));
            given(reservationMapper.cancel(RESERVATION_ID)).willReturn(1);

            ReservationResponse response =
                    reservationService.cancel(cancelRequest(RESERVATION_ID, ROOM));

            assertThat(response.getStatus()).isEqualTo(StatusUtil.STATUS_RESERVATION_CANCELLED);
        }

        @Test
        @DisplayName("존재하지 않는 예약이면 RESERVATION_NOT_FOUND")
        void cancel_unknownReservation_throwsReservationNotFound() {
            given(reservationMapper.findById(RESERVATION_ID)).willReturn(null);

            assertThatThrownBy(() ->
                    reservationService.cancel(cancelRequest(RESERVATION_ID, ROOM)))
                    .isInstanceOf(BusinessException.class)
                    .extracting(e -> ((BusinessException) e).getErrorCode())
                    .isEqualTo(ErrorCode.RESERVATION_NOT_FOUND);

            then(reservationMapper).should(never()).cancel(anyLong());
        }

        @Test
        @DisplayName("다른 방 번호로 취소를 시도하면 RESERVATION_FORBIDDEN - 방 번호가 소유 증명이다")
        void cancel_wrongRoomNumber_throwsForbidden() {
            given(reservationMapper.findById(RESERVATION_ID))
                    .willReturn(reservation(RESERVATION_ID, ROOM, StatusUtil.STATUS_RESERVATION_WAITING));

            assertThatThrownBy(() ->
                    reservationService.cancel(cancelRequest(RESERVATION_ID, "B1")))
                    .isInstanceOf(BusinessException.class)
                    .extracting(e -> ((BusinessException) e).getErrorCode())
                    .isEqualTo(ErrorCode.RESERVATION_FORBIDDEN);

            then(reservationMapper).should(never()).cancel(anyLong());
        }

        @Test
        @DisplayName("이미 이행/취소된 예약이면 (갱신 0건) RESERVATION_NOT_CANCELABLE")
        void cancel_alreadySettled_throwsNotCancelable() {
            given(reservationMapper.findById(RESERVATION_ID))
                    .willReturn(reservation(RESERVATION_ID, ROOM, StatusUtil.STATUS_RESERVATION_FULFILLED));
            // UPDATE ... AND status='WAITING' 이 0건을 반환하는 상황
            given(reservationMapper.cancel(RESERVATION_ID)).willReturn(0);

            assertThatThrownBy(() ->
                    reservationService.cancel(cancelRequest(RESERVATION_ID, ROOM)))
                    .isInstanceOf(BusinessException.class)
                    .extracting(e -> ((BusinessException) e).getErrorCode())
                    .isEqualTo(ErrorCode.RESERVATION_NOT_CANCELABLE);
        }
    }

    @Nested
    @DisplayName("방별 예약 목록")
    class FindByRoom {

        @Test
        @DisplayName("status 를 주면 그대로 매퍼에 전달한다")
        void findByRoom_withStatus_delegates() {
            List<ReservationResponse> expected =
                    List.of(reservation(1L, ROOM, StatusUtil.STATUS_RESERVATION_WAITING));
            given(reservationMapper.findByRoom(ROOM, StatusUtil.STATUS_RESERVATION_WAITING))
                    .willReturn(expected);

            assertThat(reservationService.findByRoom(ROOM, StatusUtil.STATUS_RESERVATION_WAITING))
                    .isEqualTo(expected);
        }

        @Test
        @DisplayName("status 가 null 이면 null 그대로 넘겨 전체 상태를 조회한다")
        void findByRoom_withoutStatus_passesNull() {
            given(reservationMapper.findByRoom(ROOM, null)).willReturn(List.of());

            assertThat(reservationService.findByRoom(ROOM, null)).isEmpty();
            then(reservationMapper).should().findByRoom(ROOM, null);
        }
    }
}
