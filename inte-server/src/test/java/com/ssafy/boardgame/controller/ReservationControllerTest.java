package com.ssafy.boardgame.controller;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.dto.ReservationCancelRequest;
import com.ssafy.boardgame.dto.ReservationRequest;
import com.ssafy.boardgame.dto.ReservationResponse;
import com.ssafy.boardgame.service.ReservationService;
import com.ssafy.boardgame.util.StatusUtil;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.BDDMockito.willThrow;
import static org.mockito.Mockito.never;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ReservationController.class)
@DisplayName("ReservationController - 예약 API")
class ReservationControllerTest {

    @Autowired private MockMvc mockMvc;

    @MockitoBean private ReservationService reservationService;

    private static ReservationResponse reservation(Long id, String room, String status) {
        ReservationResponse reservation = new ReservationResponse();
        reservation.setReservationId(id);
        reservation.setBoardGameId(1L);
        reservation.setBoardGameName("루미큐브");
        reservation.setRoomNumber(room);
        reservation.setStatus(status);
        return reservation;
    }

    @Nested
    @DisplayName("POST /reservation - 예약하기")
    class Reserve {

        private static String body(String boardGameId, String roomNumber) {
            return """
                    {"boardGameId": %s, "roomNumber": %s}
                    """.formatted(boardGameId,
                    roomNumber == null ? "null" : "\"" + roomNumber + "\"");
        }

        @Test
        @DisplayName("예약에 성공하면 201 과 대기 순번을 반환한다")
        void reserve_success_returns201WithWaitingRank() throws Exception {
            ReservationResponse response =
                    reservation(77L, "A1", StatusUtil.STATUS_RESERVATION_WAITING);
            response.setWaitingRank(3);
            given(reservationService.reserve(any(ReservationRequest.class))).willReturn(response);

            mockMvc.perform(post("/reservation")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(body("1", "A1")))
                    .andExpect(status().isCreated())
                    .andExpect(jsonPath("$.reservationId").value(77))
                    .andExpect(jsonPath("$.boardGameName").value("루미큐브"))
                    .andExpect(jsonPath("$.status").value(StatusUtil.STATUS_RESERVATION_WAITING))
                    .andExpect(jsonPath("$.waitingRank").value(3));
        }

        @Test
        @DisplayName("요청 본문이 서비스로 그대로 전달된다")
        void reserve_bindsRequestBody() throws Exception {
            given(reservationService.reserve(any(ReservationRequest.class)))
                    .willReturn(reservation(1L, "B1", StatusUtil.STATUS_RESERVATION_WAITING));

            mockMvc.perform(post("/reservation")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(body("42", "B1")))
                    .andExpect(status().isCreated());

            var captor = org.mockito.ArgumentCaptor.forClass(ReservationRequest.class);
            then(reservationService).should().reserve(captor.capture());
            assertThat(captor.getValue().getBoardGameId()).isEqualTo(42L);
            assertThat(captor.getValue().getRoomNumber()).isEqualTo("B1");
        }

        @ParameterizedTest(name = "{0} -> {1}")
        @CsvSource({
                "BOARD_GAME_NOT_FOUND,   404",
                "ROOM_NOT_FOUND,         404",
                "ROOM_NOT_IN_USE,        409",
                "ALREADY_RENTED,         409",
                "RESERVATION_NOT_NEEDED, 409",
                "DUPLICATE_RESERVATION,  409",
        })
        @DisplayName("비즈니스 예외는 ErrorCode 의 상태코드와 code 로 매핑된다")
        void reserve_businessException_mapsToErrorCodeStatus(String errorCodeName, int expected)
                throws Exception {
            ErrorCode errorCode = ErrorCode.valueOf(errorCodeName);
            willThrow(new BusinessException(errorCode))
                    .given(reservationService).reserve(any(ReservationRequest.class));

            mockMvc.perform(post("/reservation")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(body("1", "A1")))
                    .andExpect(status().is(expected))
                    .andExpect(jsonPath("$.code").value(errorCodeName))
                    .andExpect(jsonPath("$.message").value(errorCode.getMessage()));
        }

        @Test
        @DisplayName("동시 요청으로 유니크 인덱스가 깨지면 409 DUPLICATE_RESERVATION 으로 변환된다")
        void reserve_duplicateKey_returns409() throws Exception {
            // uq_reservation_waiting 부분 유니크 인덱스 위반이 DataAccessException 으로 올라오는 경로.
            willThrow(new DuplicateKeyException("uq_reservation_waiting"))
                    .given(reservationService).reserve(any(ReservationRequest.class));

            mockMvc.perform(post("/reservation")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(body("1", "A1")))
                    .andExpect(status().isConflict())
                    .andExpect(jsonPath("$.code").value("DUPLICATE_RESERVATION"));
        }

        @Test
        @DisplayName("boardGameId 가 없으면 400 INVALID_INPUT 이고 서비스까지 가지 않는다")
        void reserve_missingBoardGameId_returns400() throws Exception {
            mockMvc.perform(post("/reservation")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(body("null", "A1")))
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.code").value("INVALID_INPUT"))
                    .andExpect(jsonPath("$.message").value(
                            org.hamcrest.Matchers.containsString("boardGameId")));

            then(reservationService).should(never()).reserve(any(ReservationRequest.class));
        }

        @Test
        @DisplayName("roomNumber 가 비어 있으면 400 INVALID_INPUT")
        void reserve_blankRoomNumber_returns400() throws Exception {
            mockMvc.perform(post("/reservation")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(body("1", "  ")))
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
        }
    }

    @Nested
    @DisplayName("PATCH /reservation/cancel - 예약취소")
    class Cancel {

        private static String body(String reservationId, String roomNumber) {
            return """
                    {"reservationId": %s, "roomNumber": %s}
                    """.formatted(reservationId,
                    roomNumber == null ? "null" : "\"" + roomNumber + "\"");
        }

        @Test
        @DisplayName("취소에 성공하면 200 과 CANCELLED 상태를 반환한다")
        void cancel_success_returns200() throws Exception {
            given(reservationService.cancel(any(ReservationCancelRequest.class)))
                    .willReturn(reservation(77L, "A1", StatusUtil.STATUS_RESERVATION_CANCELLED));

            mockMvc.perform(patch("/reservation/cancel")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(body("77", "A1")))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.reservationId").value(77))
                    .andExpect(jsonPath("$.status").value(StatusUtil.STATUS_RESERVATION_CANCELLED));
        }

        @ParameterizedTest(name = "{0} -> {1}")
        @CsvSource({
                "RESERVATION_NOT_FOUND,      404",
                "RESERVATION_FORBIDDEN,      403",
                "RESERVATION_NOT_CANCELABLE, 409",
        })
        @DisplayName("비즈니스 예외는 ErrorCode 의 상태코드와 code 로 매핑된다")
        void cancel_businessException_mapsToErrorCodeStatus(String errorCodeName, int expected)
                throws Exception {
            ErrorCode errorCode = ErrorCode.valueOf(errorCodeName);
            willThrow(new BusinessException(errorCode))
                    .given(reservationService).cancel(any(ReservationCancelRequest.class));

            mockMvc.perform(patch("/reservation/cancel")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(body("77", "A1")))
                    .andExpect(status().is(expected))
                    .andExpect(jsonPath("$.code").value(errorCodeName));
        }

        @Test
        @DisplayName("roomNumber 가 비어 있으면 400 INVALID_INPUT - 방 번호가 소유 증명이라 필수다")
        void cancel_blankRoomNumber_returns400() throws Exception {
            mockMvc.perform(patch("/reservation/cancel")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(body("77", "  ")))
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.code").value("INVALID_INPUT"));

            then(reservationService).should(never()).cancel(any(ReservationCancelRequest.class));
        }

        @Test
        @DisplayName("reservationId 가 없으면 400 INVALID_INPUT - 404 로 뭉개지지 않는다")
        void cancel_missingReservationId_returns400() throws Exception {
            // '요청이 잘못됨'과 '예약이 없음'이 구분돼야 한다.
            // @NotNull 이 빠지면 findById(null) -> null 경로를 타 404 로 응답하게 된다.
            mockMvc.perform(patch("/reservation/cancel")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(body("null", "A1")))
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.code").value("INVALID_INPUT"))
                    .andExpect(jsonPath("$.message").value(
                            org.hamcrest.Matchers.containsString("reservationId")));

            then(reservationService).should(never()).cancel(any(ReservationCancelRequest.class));
        }
    }

    @Nested
    @DisplayName("GET /reservation - 방별 예약 목록")
    class FindByRoom {

        @Test
        @DisplayName("roomNumber 만 주면 status 는 null 로 전달되어 전체 상태를 조회한다")
        void findByRoom_withoutStatus_passesNull() throws Exception {
            given(reservationService.findByRoom(eq("A1"), isNull()))
                    .willReturn(List.of(
                            reservation(1L, "A1", StatusUtil.STATUS_RESERVATION_WAITING),
                            reservation(2L, "A1", StatusUtil.STATUS_RESERVATION_CANCELLED)));

            mockMvc.perform(get("/reservation").param("roomNumber", "A1"))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.length()").value(2))
                    .andExpect(jsonPath("$[0].reservationId").value(1))
                    .andExpect(jsonPath("$[1].status").value(StatusUtil.STATUS_RESERVATION_CANCELLED));

            then(reservationService).should().findByRoom("A1", null);
        }

        @Test
        @DisplayName("status 를 주면 그대로 전달된다")
        void findByRoom_withStatus_delegates() throws Exception {
            given(reservationService.findByRoom("A1", StatusUtil.STATUS_RESERVATION_WAITING))
                    .willReturn(List.of(
                            reservation(1L, "A1", StatusUtil.STATUS_RESERVATION_WAITING)));

            mockMvc.perform(get("/reservation")
                            .param("roomNumber", "A1")
                            .param("status", StatusUtil.STATUS_RESERVATION_WAITING))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.length()").value(1))
                    .andExpect(jsonPath("$[0].status").value(StatusUtil.STATUS_RESERVATION_WAITING));
        }

        @Test
        @DisplayName("예약이 없으면 빈 배열을 반환한다")
        void findByRoom_noReservations_returnsEmptyArray() throws Exception {
            given(reservationService.findByRoom(eq("B1"), isNull())).willReturn(List.of());

            mockMvc.perform(get("/reservation").param("roomNumber", "B1"))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.length()").value(0));
        }

        @Test
        @DisplayName("roomNumber 가 없으면 400 - 필수 파라미터다")
        void findByRoom_missingRoomNumber_returns400() throws Exception {
            mockMvc.perform(get("/reservation"))
                    .andExpect(status().isBadRequest());
        }
    }
}
