package com.ssafy.boardgame.service;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.dto.RoomRequest;
import com.ssafy.boardgame.dto.RoomResponse;
import com.ssafy.boardgame.dto.RoomUsageRequest;
import com.ssafy.boardgame.dto.RoomUsageResponse;
import com.ssafy.boardgame.mapper.BoardGameItemMapper;
import com.ssafy.boardgame.mapper.RentMapper;
import com.ssafy.boardgame.mapper.ReservationMapper;
import com.ssafy.boardgame.mapper.RoomMapper;
import com.ssafy.boardgame.mapper.RoomUsageMapper;
import com.ssafy.boardgame.util.StatusUtil;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InOrder;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verifyNoInteractions;

import java.time.LocalDateTime;

@ExtendWith(MockitoExtension.class)
@DisplayName("AdminService - 룸 상태변경")
class AdminServiceTest {

    private static final String ROOM = "A1";

    @Mock private RoomMapper roomMapper;
    @Mock private RoomUsageMapper roomUsageMapper;
    @Mock private RentMapper rentMapper;
    @Mock private BoardGameItemMapper boardGameItemMapper;
    @Mock private ReservationMapper reservationMapper;
    @Mock private ReservationNotifyService reservationNotifyService;

    @InjectMocks private AdminService adminService;

    private static RoomRequest request(String roomNumber, String status) {
        RoomRequest request = new RoomRequest();
        request.setRoomNumber(roomNumber);
        request.setStatus(status);
        return request;
    }

    private static RoomUsageRequest usageRequest(String roomNumber) {
        RoomUsageRequest request = new RoomUsageRequest();
        request.setRoomNumber(roomNumber);
        return request;
    }

    private static RoomResponse room(String roomNumber, String status) {
        RoomResponse room = new RoomResponse();
        room.setRoomNumber(roomNumber);
        room.setCapacity(6);
        room.setStatus(status);
        return room;
    }

    private static RoomUsageResponse usage(Long id, String roomNumber, LocalDateTime endTime) {
        RoomUsageResponse usage = new RoomUsageResponse();
        usage.setRoomUsageId(id);
        usage.setRoomNumber(roomNumber);
        usage.setStartTime(LocalDateTime.of(2026, 7, 30, 13, 0));
        usage.setEndTime(endTime);
        return usage;
    }

    @Nested
    @DisplayName("퇴실(EMPTY)로 변경할 때")
    class CheckOut {

        @Test
        @DisplayName("사본 반납 → 대여 마감 → 예약 취소 순서로 정리한다")
        void checkOut_cleansUpInStrictOrder() {
            given(roomMapper.findByRoomNumber(ROOM))
                    .willReturn(room(ROOM, StatusUtil.STATUS_ROOM_USE),
                                room(ROOM, StatusUtil.STATUS_ROOM_EMPTY));

            adminService.updateRoomStatus(request(ROOM, StatusUtil.STATUS_ROOM_EMPTY));

            // 순서가 뒤집히면 rent 가 먼저 마감돼 releaseByRoom 이 대상 사본을 못 찾고
            // 재고가 RENTED 로 영구히 묶인다. 이 테스트가 그 회귀를 막는다.
            InOrder inOrder = inOrder(boardGameItemMapper, rentMapper, reservationMapper);
            inOrder.verify(boardGameItemMapper).releaseByRoom(ROOM);
            inOrder.verify(rentMapper).returnAllByRoom(ROOM);
            inOrder.verify(reservationMapper).cancelAllByRoom(ROOM);
            inOrder.verifyNoMoreInteractions();
        }

        @Test
        @DisplayName("상태를 EMPTY 로 갱신하고 갱신된 방을 반환한다")
        void checkOut_updatesStatusAndReturnsFreshRoom() {
            given(roomMapper.findByRoomNumber(ROOM))
                    .willReturn(room(ROOM, StatusUtil.STATUS_ROOM_USE),
                                room(ROOM, StatusUtil.STATUS_ROOM_EMPTY));

            RoomResponse result =
                    adminService.updateRoomStatus(request(ROOM, StatusUtil.STATUS_ROOM_EMPTY));

            then(roomMapper).should().updateRoomStatus(ROOM, StatusUtil.STATUS_ROOM_EMPTY);
            assertThat(result.getRoomNumber()).isEqualTo(ROOM);
            assertThat(result.getStatus()).isEqualTo(StatusUtil.STATUS_ROOM_EMPTY);
        }

        @Test
        @DisplayName("정리할 대여/예약이 없어도 (전부 0건) 정상 처리된다")
        void checkOut_isSafeWhenNothingToCleanUp() {
            given(roomMapper.findByRoomNumber(ROOM))
                    .willReturn(room(ROOM, StatusUtil.STATUS_ROOM_EMPTY),
                                room(ROOM, StatusUtil.STATUS_ROOM_EMPTY));
            given(boardGameItemMapper.releaseByRoom(ROOM)).willReturn(0);
            given(rentMapper.returnAllByRoom(ROOM)).willReturn(0);
            given(reservationMapper.cancelAllByRoom(ROOM)).willReturn(0);

            RoomResponse result =
                    adminService.updateRoomStatus(request(ROOM, StatusUtil.STATUS_ROOM_EMPTY));

            assertThat(result.getStatus()).isEqualTo(StatusUtil.STATUS_ROOM_EMPTY);
        }

        @Test
        @DisplayName("이미 EMPTY 인 방에 다시 요청해도 정리를 그대로 수행한다 (멱등)")
        void checkOut_isIdempotentOnAlreadyEmptyRoom() {
            given(roomMapper.findByRoomNumber(ROOM))
                    .willReturn(room(ROOM, StatusUtil.STATUS_ROOM_EMPTY),
                                room(ROOM, StatusUtil.STATUS_ROOM_EMPTY));

            adminService.updateRoomStatus(request(ROOM, StatusUtil.STATUS_ROOM_EMPTY));

            // 정리 쿼리들이 조건부(returned_at IS NULL / status='WAITING')라 재실행이 안전하다는
            // 설계를 서비스 레벨에서도 고정한다. 상태 갱신 누락으로 엉킨 방의 강제 정리 경로이기도 하다.
            then(boardGameItemMapper).should().releaseByRoom(ROOM);
            then(rentMapper).should().returnAllByRoom(ROOM);
            then(reservationMapper).should().cancelAllByRoom(ROOM);
        }

        @Test
        @DisplayName("API 표기인 대문자 EMPTY 로 들어와도 소문자로 저장하고 정리를 수행한다")
        void checkOut_normalizesUppercaseStatus() {
            given(roomMapper.findByRoomNumber(ROOM))
                    .willReturn(room(ROOM, StatusUtil.STATUS_ROOM_USE),
                                room(ROOM, StatusUtil.STATUS_ROOM_EMPTY));

            // RoomRequest 의 @Pattern 은 대문자만 통과시키므로 컨트롤러를 거쳐 오면 항상 이 값이다.
            // 그대로 저장하면 status 비교가 어긋나 퇴실 정리가 통째로 누락됐었다.
            adminService.updateRoomStatus(request(ROOM, "EMPTY"));

            then(roomMapper).should().updateRoomStatus(ROOM, StatusUtil.STATUS_ROOM_EMPTY);
            then(boardGameItemMapper).should().releaseByRoom(ROOM);
            then(rentMapper).should().returnAllByRoom(ROOM);
            then(reservationMapper).should().cancelAllByRoom(ROOM);
        }
    }

    @Nested
    @DisplayName("사용(USE)으로 변경할 때")
    class CheckIn {

        @Test
        @DisplayName("대여/예약 정리를 전혀 하지 않는다")
        void checkIn_doesNotCleanUp() {
            given(roomMapper.findByRoomNumber(ROOM))
                    .willReturn(room(ROOM, StatusUtil.STATUS_ROOM_EMPTY),
                                room(ROOM, StatusUtil.STATUS_ROOM_USE));

            RoomResponse result =
                    adminService.updateRoomStatus(request(ROOM, StatusUtil.STATUS_ROOM_USE));

            verifyNoInteractions(rentMapper, boardGameItemMapper, reservationMapper);
            then(roomMapper).should().updateRoomStatus(ROOM, StatusUtil.STATUS_ROOM_USE);
            assertThat(result.getStatus()).isEqualTo(StatusUtil.STATUS_ROOM_USE);
        }

        @Test
        @DisplayName("room_usage 는 건드리지 않는다 (이용 이력은 checkIn/checkOut 담당)")
        void updateRoomStatus_doesNotTouchRoomUsage() {
            given(roomMapper.findByRoomNumber(ROOM))
                    .willReturn(room(ROOM, StatusUtil.STATUS_ROOM_EMPTY),
                                room(ROOM, StatusUtil.STATUS_ROOM_USE));

            adminService.updateRoomStatus(request(ROOM, StatusUtil.STATUS_ROOM_USE));

            verifyNoInteractions(roomUsageMapper);
        }

        @Test
        @DisplayName("API 표기인 대문자 USE 로 들어와도 소문자로 저장한다")
        void checkIn_normalizesUppercaseStatus() {
            given(roomMapper.findByRoomNumber(ROOM))
                    .willReturn(room(ROOM, StatusUtil.STATUS_ROOM_EMPTY),
                                room(ROOM, StatusUtil.STATUS_ROOM_USE));

            adminService.updateRoomStatus(request(ROOM, "USE"));

            // 대문자로 저장되면 RentService/ReservationService 의 '이용 중' 판정(STATUS_ROOM_USE 비교)이
            // 어긋나 이 방의 대여·예약이 전부 ROOM_NOT_IN_USE 로 거부된다.
            then(roomMapper).should().updateRoomStatus(ROOM, StatusUtil.STATUS_ROOM_USE);
        }
    }

    @Test
    @DisplayName("존재하지 않는 방이면 ROOM_NOT_FOUND 이고 상태 변경도 정리도 하지 않는다")
    void updateRoomStatus_unknownRoom_throwsRoomNotFound() {
        given(roomMapper.findByRoomNumber("Z9")).willReturn(null);

        assertThatThrownBy(() ->
                adminService.updateRoomStatus(request("Z9", StatusUtil.STATUS_ROOM_EMPTY)))
                .isInstanceOf(BusinessException.class)
                .extracting(e -> ((BusinessException) e).getErrorCode())
                .isEqualTo(ErrorCode.ROOM_NOT_FOUND);

        then(roomMapper).should(never()).updateRoomStatus(anyString(), anyString());
        verifyNoInteractions(rentMapper, boardGameItemMapper, reservationMapper);
    }

    @Nested
    @DisplayName("입실 API (checkIn)")
    class CheckInApi {

        @Test
        @DisplayName("이용 이력을 만들고 방을 USE 로 바꾼다")
        void checkIn_insertsUsageAndSetsRoomInUse() {
            given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(ROOM, StatusUtil.STATUS_ROOM_EMPTY));
            given(roomUsageMapper.insertIfAbsent(ROOM)).willReturn(1);
            given(roomUsageMapper.findOpenByRoom(ROOM)).willReturn(usage(10L, ROOM, null));

            RoomUsageResponse result = adminService.checkIn(usageRequest(ROOM));

            then(roomUsageMapper).should().insertIfAbsent(ROOM);
            then(roomMapper).should().updateRoomStatus(ROOM, StatusUtil.STATUS_ROOM_USE);
            assertThat(result.getRoomUsageId()).isEqualTo(10L);
            assertThat(result.getEndTime()).isNull();
            assertThat(result.getRoomStatus()).isEqualTo(StatusUtil.STATUS_ROOM_USE);
        }

        @Test
        @DisplayName("입실은 대여/예약을 정리하지 않는다")
        void checkIn_doesNotCleanUp() {
            given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(ROOM, StatusUtil.STATUS_ROOM_EMPTY));
            given(roomUsageMapper.findOpenByRoom(ROOM)).willReturn(usage(10L, ROOM, null));

            adminService.checkIn(usageRequest(ROOM));

            verifyNoInteractions(rentMapper, boardGameItemMapper, reservationMapper);
        }

        @Test
        @DisplayName("이미 이용 중이면 insert 가 0건이어도 기존 이용건을 반환한다 (멱등)")
        void checkIn_isIdempotentWhenAlreadyInUse() {
            given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(ROOM, StatusUtil.STATUS_ROOM_USE));
            // insertIfAbsent 의 NOT EXISTS 가 걸려 0건. 기존 열린 이용건이 그대로 살아 있어야 한다.
            given(roomUsageMapper.insertIfAbsent(ROOM)).willReturn(0);
            given(roomUsageMapper.findOpenByRoom(ROOM)).willReturn(usage(7L, ROOM, null));

            RoomUsageResponse result = adminService.checkIn(usageRequest(ROOM));

            assertThat(result.getRoomUsageId()).isEqualTo(7L);
            assertThat(result.getStartTime()).isEqualTo(LocalDateTime.of(2026, 7, 30, 13, 0));
        }

        @Test
        @DisplayName("존재하지 않는 방이면 ROOM_NOT_FOUND 이고 아무것도 쓰지 않는다")
        void checkIn_unknownRoom_throwsRoomNotFound() {
            given(roomMapper.findByRoomNumber("Z9")).willReturn(null);

            assertThatThrownBy(() -> adminService.checkIn(usageRequest("Z9")))
                    .isInstanceOf(BusinessException.class)
                    .extracting(e -> ((BusinessException) e).getErrorCode())
                    .isEqualTo(ErrorCode.ROOM_NOT_FOUND);

            then(roomMapper).should(never()).updateRoomStatus(anyString(), anyString());
            verifyNoInteractions(roomUsageMapper);
        }
    }

    @Nested
    @DisplayName("퇴실 API (checkOut)")
    class CheckOutApi {

        @Test
        @DisplayName("end_time 을 닫고 방을 EMPTY 로 바꾼다")
        void checkOut_closesUsageAndEmptiesRoom() {
            LocalDateTime ended = LocalDateTime.of(2026, 7, 30, 15, 30);
            given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(ROOM, StatusUtil.STATUS_ROOM_USE));
            given(roomUsageMapper.closeByRoom(ROOM)).willReturn(1);
            given(roomUsageMapper.findLatestByRoom(ROOM)).willReturn(usage(10L, ROOM, ended));

            RoomUsageResponse result = adminService.checkOut(usageRequest(ROOM));

            then(roomUsageMapper).should().closeByRoom(ROOM);
            then(roomMapper).should().updateRoomStatus(ROOM, StatusUtil.STATUS_ROOM_EMPTY);
            assertThat(result.getEndTime()).isEqualTo(ended);
            assertThat(result.getRoomStatus()).isEqualTo(StatusUtil.STATUS_ROOM_EMPTY);
        }

        @Test
        @DisplayName("대여/예약도 사본 반납 → 대여 마감 → 예약 취소 순으로 정리한다")
        void checkOut_cleansUpInStrictOrder() {
            given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(ROOM, StatusUtil.STATUS_ROOM_USE));
            given(roomUsageMapper.findLatestByRoom(ROOM))
                    .willReturn(usage(10L, ROOM, LocalDateTime.of(2026, 7, 30, 15, 30)));

            adminService.checkOut(usageRequest(ROOM));

            // 이 정리를 빼면 퇴실한 방의 사본이 RENTED 로 영구히 묶인다. 순서까지 고정한다.
            InOrder inOrder = inOrder(boardGameItemMapper, rentMapper, reservationMapper);
            inOrder.verify(boardGameItemMapper).releaseByRoom(ROOM);
            inOrder.verify(rentMapper).returnAllByRoom(ROOM);
            inOrder.verify(reservationMapper).cancelAllByRoom(ROOM);
            inOrder.verifyNoMoreInteractions();
        }

        @Test
        @DisplayName("이미 퇴실한 방에 다시 요청해도 0건 처리되고 실패하지 않는다 (멱등)")
        void checkOut_isIdempotent() {
            given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(ROOM, StatusUtil.STATUS_ROOM_EMPTY));
            given(roomUsageMapper.closeByRoom(ROOM)).willReturn(0);
            given(roomUsageMapper.findLatestByRoom(ROOM))
                    .willReturn(usage(10L, ROOM, LocalDateTime.of(2026, 7, 30, 15, 30)));

            RoomUsageResponse result = adminService.checkOut(usageRequest(ROOM));

            assertThat(result.getRoomStatus()).isEqualTo(StatusUtil.STATUS_ROOM_EMPTY);
        }

        @Test
        @DisplayName("이용 이력이 없는 방(입실 누락)이어도 null 응답 없이 방 정보를 채워 반환한다")
        void checkOut_withoutAnyUsageHistory_stillReturnsRoomInfo() {
            given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(ROOM, StatusUtil.STATUS_ROOM_USE));
            given(roomUsageMapper.findLatestByRoom(ROOM)).willReturn(null);

            RoomUsageResponse result = adminService.checkOut(usageRequest(ROOM));

            assertThat(result).isNotNull();
            assertThat(result.getRoomNumber()).isEqualTo(ROOM);
            assertThat(result.getRoomStatus()).isEqualTo(StatusUtil.STATUS_ROOM_EMPTY);
            assertThat(result.getRoomUsageId()).isNull();
        }

        @Test
        @DisplayName("존재하지 않는 방이면 ROOM_NOT_FOUND 이고 아무것도 쓰지 않는다")
        void checkOut_unknownRoom_throwsRoomNotFound() {
            given(roomMapper.findByRoomNumber("Z9")).willReturn(null);

            assertThatThrownBy(() -> adminService.checkOut(usageRequest("Z9")))
                    .isInstanceOf(BusinessException.class)
                    .extracting(e -> ((BusinessException) e).getErrorCode())
                    .isEqualTo(ErrorCode.ROOM_NOT_FOUND);

            then(roomMapper).should(never()).updateRoomStatus(anyString(), anyString());
            verifyNoInteractions(roomUsageMapper, rentMapper, boardGameItemMapper, reservationMapper);
        }
    }
}
