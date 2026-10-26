package com.ssafy.boardgame.controller;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.dto.BoardGameItem;
import com.ssafy.boardgame.dto.RentRequest;
import com.ssafy.boardgame.dto.RentResponse;
import com.ssafy.boardgame.service.RentService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.BDDMockito.willThrow;
import static org.mockito.Mockito.never;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RentController.class)
@DisplayName("POST /rent - 보드게임 대여")
class RentControllerTest {

    @Autowired private MockMvc mockMvc;

    @MockitoBean private RentService rentService;

    private static String body(String boardGameId, String roomNumber) {
        return """
                {"boardGameId": %s, "roomNumber": %s}
                """.formatted(boardGameId, roomNumber == null ? "null" : "\"" + roomNumber + "\"");
    }

    private static RentResponse rentResponse() {
        BoardGameItem item = new BoardGameItem();
        item.setItemId(10L);
        item.setBoardGameId(1L);
        item.setCabinetId(3L);
        RentResponse response = RentResponse.of(1L, "루미큐브", item, "A1");
        response.setRentId(100L);
        return response;
    }

    @Test
    @DisplayName("대여에 성공하면 201 과 대여 정보를 반환한다")
    void rent_success_returns201() throws Exception {
        given(rentService.rent(any(RentRequest.class))).willReturn(rentResponse());

        mockMvc.perform(post("/rent")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("1", "A1")))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.rentId").value(100))
                .andExpect(jsonPath("$.boardGameId").value(1))
                .andExpect(jsonPath("$.boardGameName").value("루미큐브"))
                .andExpect(jsonPath("$.boardGameItemId").value(10))
                // 프론트가 캐비넷을 열려면 cabinetId 가 응답에 있어야 한다.
                .andExpect(jsonPath("$.cabinetId").value(3))
                .andExpect(jsonPath("$.roomNumber").value("A1"));
    }

    @Test
    @DisplayName("요청 본문이 서비스로 그대로 전달된다")
    void rent_bindsRequestBody() throws Exception {
        given(rentService.rent(any(RentRequest.class))).willReturn(rentResponse());

        mockMvc.perform(post("/rent")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("42", "B1")))
                .andExpect(status().isCreated());

        var captor = org.mockito.ArgumentCaptor.forClass(RentRequest.class);
        then(rentService).should().rent(captor.capture());
        assertThat(captor.getValue().getBoardGameId()).isEqualTo(42L);
        assertThat(captor.getValue().getRoomNumber()).isEqualTo("B1");
    }

    @ParameterizedTest(name = "{0} -> {1}")
    @CsvSource({
            "BOARD_GAME_NOT_FOUND,    404",
            "ROOM_NOT_FOUND,          404",
            "ROOM_NOT_IN_USE,         409",
            "ALREADY_RENTED,          409",
            "BOARD_GAME_OUT_OF_STOCK, 409",
    })
    @DisplayName("비즈니스 예외는 ErrorCode 의 상태코드와 code 로 매핑된다")
    void rent_businessException_mapsToErrorCodeStatus(String errorCodeName, int expectedStatus)
            throws Exception {
        ErrorCode errorCode = ErrorCode.valueOf(errorCodeName);
        willThrow(new BusinessException(errorCode))
                .given(rentService).rent(any(RentRequest.class));

        mockMvc.perform(post("/rent")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("1", "A1")))
                .andExpect(status().is(expectedStatus))
                .andExpect(jsonPath("$.code").value(errorCodeName))
                .andExpect(jsonPath("$.message").value(errorCode.getMessage()));
    }

    @Test
    @DisplayName("boardGameId 가 없으면 400 INVALID_INPUT 이고 서비스까지 가지 않는다")
    void rent_missingBoardGameId_returns400() throws Exception {
        mockMvc.perform(post("/rent")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("null", "A1")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"))
                .andExpect(jsonPath("$.message").value(
                        org.hamcrest.Matchers.containsString("boardGameId")));

        then(rentService).should(never()).rent(any(RentRequest.class));
    }

    @Test
    @DisplayName("roomNumber 가 비어 있으면 400 INVALID_INPUT")
    void rent_blankRoomNumber_returns400() throws Exception {
        mockMvc.perform(post("/rent")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("1", "   ")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"))
                .andExpect(jsonPath("$.message").value(
                        org.hamcrest.Matchers.containsString("roomNumber")));
    }

    @Test
    @DisplayName("roomNumber 가 10자를 넘으면 400 INVALID_INPUT")
    void rent_tooLongRoomNumber_returns400() throws Exception {
        mockMvc.perform(post("/rent")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("1", "12345678901")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    @DisplayName("두 필드가 모두 잘못되면 메시지에 둘 다 담긴다")
    void rent_multipleViolations_reportsAll() throws Exception {
        mockMvc.perform(post("/rent")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("null", "")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value(
                        org.hamcrest.Matchers.allOf(
                                org.hamcrest.Matchers.containsString("boardGameId"),
                                org.hamcrest.Matchers.containsString("roomNumber"))));
    }
}
