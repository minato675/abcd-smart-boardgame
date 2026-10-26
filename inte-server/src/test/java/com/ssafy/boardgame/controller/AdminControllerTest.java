package com.ssafy.boardgame.controller;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.dto.RoomRequest;
import com.ssafy.boardgame.dto.RoomResponse;
import com.ssafy.boardgame.service.AdminService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
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

@WebMvcTest(AdminController.class)
@DisplayName("POST /admin/room/update - 룸 상태변경")
class AdminControllerTest {

    @Autowired private MockMvc mockMvc;

    @MockitoBean private AdminService adminService;

    private static String body(String roomNumber, String status) {
        return """
                {"roomNumber": %s, "status": %s}
                """.formatted(quote(roomNumber), quote(status));
    }

    private static String quote(String value) {
        return value == null ? "null" : "\"" + value + "\"";
    }

    private static RoomResponse room(String roomNumber, String status) {
        RoomResponse room = new RoomResponse();
        room.setRoomNumber(roomNumber);
        room.setCapacity(6);
        room.setStatus(status);
        return room;
    }

    @Test
    @DisplayName("퇴실 처리에 성공하면 200 과 갱신된 방 정보를 반환한다")
    void updateRoomStatus_checkOut_returns200() throws Exception {
        given(adminService.updateRoomStatus(any(RoomRequest.class)))
                .willReturn(room("A1", "EMPTY"));

        mockMvc.perform(post("/admin/room/update")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("A1", "EMPTY")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.roomNumber").value("A1"))
                .andExpect(jsonPath("$.capacity").value(6))
                .andExpect(jsonPath("$.status").value("EMPTY"));
    }

    @Test
    @DisplayName("입실 처리도 같은 엔드포인트로 200 을 반환한다")
    void updateRoomStatus_checkIn_returns200() throws Exception {
        given(adminService.updateRoomStatus(any(RoomRequest.class)))
                .willReturn(room("A1", "USE"));

        mockMvc.perform(post("/admin/room/update")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("A1", "USE")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("USE"));
    }

    @Test
    @DisplayName("응답의 상태 필드명은 요청과 같은 'status' 다 - 대문자 'Status' 로 회귀하지 않는다")
    void updateRoomStatus_responseFieldIsLowercase() throws Exception {
        // RoomResponse 의 필드를 `private String Status;` 로 되돌리면 직렬화 결과가
        // {"Status":...} 가 되어 요청 DTO(status) 및 다른 DTO(camelCase)와 어긋난다.
        given(adminService.updateRoomStatus(any(RoomRequest.class)))
                .willReturn(room("A1", "EMPTY"));

        mockMvc.perform(post("/admin/room/update")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("A1", "EMPTY")))
                .andExpect(jsonPath("$.status").value("EMPTY"))
                .andExpect(jsonPath("$.Status").doesNotExist());
    }

    @Test
    @DisplayName("요청 본문의 roomNumber/status 가 서비스로 그대로 전달된다")
    void updateRoomStatus_bindsRequestBody() throws Exception {
        given(adminService.updateRoomStatus(any(RoomRequest.class)))
                .willReturn(room("B1", "EMPTY"));

        mockMvc.perform(post("/admin/room/update")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("B1", "EMPTY")))
                .andExpect(status().isOk());

        var captor = org.mockito.ArgumentCaptor.forClass(RoomRequest.class);
        then(adminService).should().updateRoomStatus(captor.capture());
        assertThat(captor.getValue().getRoomNumber()).isEqualTo("B1");
        assertThat(captor.getValue().getStatus()).isEqualTo("EMPTY");
    }

    @Test
    @DisplayName("존재하지 않는 방이면 404 ROOM_NOT_FOUND")
    void updateRoomStatus_unknownRoom_returns404() throws Exception {
        willThrow(new BusinessException(ErrorCode.ROOM_NOT_FOUND))
                .given(adminService).updateRoomStatus(any(RoomRequest.class));

        mockMvc.perform(post("/admin/room/update")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("Z9", "EMPTY")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("ROOM_NOT_FOUND"))
                .andExpect(jsonPath("$.message").value("존재하지 않는 방 번호입니다."));
    }

    @ParameterizedTest(name = "status={0}")
    @ValueSource(strings = {"IN_USE", "MAINTENANCE", "empty", "use", "OPEN", ""})
    @DisplayName("허용되지 않은 status 는 400 INVALID_INPUT 이고 서비스까지 가지 않는다")
    void updateRoomStatus_invalidStatus_returns400(String status) throws Exception {
        mockMvc.perform(post("/admin/room/update")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("A1", status)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"));

        then(adminService).should(never()).updateRoomStatus(any(RoomRequest.class));
    }

    @Test
    @DisplayName("status 가 없으면 400 INVALID_INPUT")
    void updateRoomStatus_missingStatus_returns400() throws Exception {
        mockMvc.perform(post("/admin/room/update")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("A1", null)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"))
                .andExpect(jsonPath("$.message").value(
                        org.hamcrest.Matchers.containsString("status")));
    }

    @Test
    @DisplayName("roomNumber 가 비어 있으면 400 INVALID_INPUT")
    void updateRoomStatus_blankRoomNumber_returns400() throws Exception {
        mockMvc.perform(post("/admin/room/update")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("  ", "EMPTY")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"))
                .andExpect(jsonPath("$.message").value(
                        org.hamcrest.Matchers.containsString("roomNumber")));
    }

    @Test
    @DisplayName("roomNumber 가 10자를 넘으면 400 INVALID_INPUT")
    void updateRoomStatus_tooLongRoomNumber_returns400() throws Exception {
        mockMvc.perform(post("/admin/room/update")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body("12345678901", "EMPTY")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }
}
