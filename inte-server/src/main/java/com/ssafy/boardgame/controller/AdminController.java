package com.ssafy.boardgame.controller;

import com.ssafy.boardgame.common.ErrorResponse;
import com.ssafy.boardgame.dto.RoomRequest;
import com.ssafy.boardgame.dto.RoomResponse;
import com.ssafy.boardgame.dto.RoomUsageRequest;
import com.ssafy.boardgame.dto.RoomUsageResponse;
import com.ssafy.boardgame.service.AdminService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Slf4j
@RestController
@RequiredArgsConstructor
@RequestMapping("admin")
@Tag(name = "관리자 - 룸", description = "룸 상태 변경 및 입실 / 퇴실 처리")
public class AdminController {
    private final AdminService adminService;
    /**
     * 룸 상태 변경 (사용/퇴실)
     *
     * room.status 만 바꾼다. 이용 이력(room_usage)까지 남기려면 /room/checkin, /room/checkout 을 쓸 것.
     */
    @Operation(summary = "룸 상태 변경",
            description = """
                    room.status 만 변경한다. 이용 이력(room_usage)까지 남겨야 한다면
                    `/admin/room/checkin` · `/admin/room/checkout` 을 사용할 것.
                    """)
    @ApiResponse(responseCode = "200", description = "상태 변경 성공")
    @ApiResponse(responseCode = "400", description = "INVALID_INPUT - 요청 값 검증 실패",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @ApiResponse(responseCode = "404", description = "ROOM_NOT_FOUND - 존재하지 않는 방 번호",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @PostMapping("/room/update")
    public RoomResponse updateRoomStatus(@RequestBody @Valid RoomRequest roomRequest) {
        return adminService.updateRoomStatus(roomRequest);
    }

    /**
     * 입실. room_usage 에 이용 이력을 생성하고 room.status 를 USE 로 변경한다.
     * 이미 이용 중인 방이면 기존 이용건을 그대로 반환한다(멱등).
     */
    @Operation(summary = "입실",
            description = """
                    room_usage 에 이용 이력을 생성하고 room.status 를 use 로 변경한다.
                    이미 이용 중인 방이면 기존 이용건을 그대로 반환한다(멱등).
                    """)
    @ApiResponse(responseCode = "200", description = "입실 처리 성공")
    @ApiResponse(responseCode = "400", description = "INVALID_INPUT - 요청 값 검증 실패",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @ApiResponse(responseCode = "404", description = "ROOM_NOT_FOUND - 존재하지 않는 방 번호",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @PostMapping("/room/checkin")
    public RoomUsageResponse checkIn(@RequestBody @Valid RoomUsageRequest request) {
        return adminService.checkIn(request);
    }

    /**
     * 퇴실. room_usage 의 end_time 을 현재시간으로 닫고 room.status 를 EMPTY 로 변경한다.
     * 그 방이 남긴 대여/예약도 함께 마감한다.
     */
    @Operation(summary = "퇴실",
            description = """
                    room_usage 의 end_time 을 현재시각으로 닫고 room.status 를 empty 로 변경한다.
                    그 방이 남긴 대여·예약도 함께 마감한다.
                    """)
    @ApiResponse(responseCode = "200", description = "퇴실 처리 성공")
    @ApiResponse(responseCode = "400", description = "INVALID_INPUT - 요청 값 검증 실패",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @ApiResponse(responseCode = "404", description = "ROOM_NOT_FOUND - 존재하지 않는 방 번호",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @PostMapping("/room/checkout")
    public RoomUsageResponse checkOut(@RequestBody @Valid RoomUsageRequest request) {
        return adminService.checkOut(request);
    }

    /**
     * 조회. 이 방의 가장 최근 이용 이력(room_usage) 한 건을 돌려준다.
     * 손님 화면 헤더가 태블릿 가동 시간이 아니라 실제 입실 시각(startTime) 기준으로
     * 이용 시간을 계산할 때 쓴다.
     */
    @Operation(summary = "이용 이력 조회",
            description = """
                    room_usage 에서 이 방 번호의 가장 최근 건(start_time 기준) 하나를 돌려준다.
                    이용 이력이 없으면 startTime/endTime 이 null 이다.
                    """)
    @ApiResponse(responseCode = "200", description = "조회 성공")
    @ApiResponse(responseCode = "404", description = "ROOM_NOT_FOUND - 존재하지 않는 방 번호",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @GetMapping("/room/usage")
    public RoomUsageResponse getUsage(@RequestParam String roomNumber) {
        return adminService.getLatestUsage(roomNumber);
    }
}
