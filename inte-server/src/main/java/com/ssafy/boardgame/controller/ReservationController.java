package com.ssafy.boardgame.controller;

import com.ssafy.boardgame.common.ErrorResponse;
import com.ssafy.boardgame.dto.ReservationCancelRequest;
import com.ssafy.boardgame.dto.ReservationRequest;
import com.ssafy.boardgame.dto.ReservationResponse;
import com.ssafy.boardgame.service.ReservationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@Slf4j
@RestController
@RequestMapping("/reservation")
@RequiredArgsConstructor
@Tag(name = "예약", description = "재고가 없는 보드게임의 예약 등록 / 취소 / 조회")
public class ReservationController {

    private final ReservationService reservationService;

    /** 보드게임 예약하기 */
    @Operation(summary = "보드게임 예약",
            description = "재고가 없어 즉시 대여할 수 없는 보드게임을 예약한다. 바로 대여 가능한 경우 409 로 거절된다.")
    @ApiResponse(responseCode = "201", description = "예약 생성 성공")
    @ApiResponse(responseCode = "400", description = "INVALID_INPUT - 요청 값 검증 실패",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @ApiResponse(responseCode = "404", description = "BOARD_GAME_NOT_FOUND / ROOM_NOT_FOUND",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @ApiResponse(responseCode = "409",
            description = "RESERVATION_NOT_NEEDED - 바로 대여 가능 / DUPLICATE_RESERVATION - 이미 예약 대기 중 / ROOM_NOT_IN_USE - 입실하지 않은 방",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ReservationResponse reserve(@Valid @RequestBody ReservationRequest request) {
        return reservationService.reserve(request);
    }

    /** 보드게임 예약취소 (soft cancel - status 변경 + cancelled_at 기록) */
    @Operation(summary = "보드게임 예약 취소",
            description = """
                    soft cancel 방식으로 status 를 변경하고 cancelled_at 을 기록한다(행을 삭제하지 않는다).
                    인증이 없으므로 요청의 roomNumber 가 예약 소유 증명 역할을 한다.
                    """)
    @ApiResponse(responseCode = "200", description = "취소 성공")
    @ApiResponse(responseCode = "400", description = "INVALID_INPUT - 요청 값 검증 실패",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @ApiResponse(responseCode = "403", description = "RESERVATION_FORBIDDEN - 다른 방의 예약",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @ApiResponse(responseCode = "404", description = "RESERVATION_NOT_FOUND - 존재하지 않는 예약",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @ApiResponse(responseCode = "409", description = "RESERVATION_NOT_CANCELABLE - 대기 중이 아닌 예약",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @PatchMapping("/cancel")
    public ReservationResponse cancel(@Valid @RequestBody ReservationCancelRequest request) {
        return reservationService.cancel(request);
    }

    /** 방별 예약 목록 (프론트가 취소할 reservationId 를 찾는 용도) */
    @Operation(summary = "방별 예약 목록 조회",
            description = "프론트가 취소 대상 reservationId 를 찾는 용도. status 를 주면 해당 상태만 필터링한다.")
    @ApiResponse(responseCode = "200", description = "조회 성공 (예약이 없으면 빈 배열)")
    @GetMapping
    public List<ReservationResponse> findByRoom(
            @Parameter(description = "방 번호", example = "A1", required = true)
            @RequestParam String roomNumber,
            @Parameter(description = "예약 상태 필터. 생략하면 전체 상태를 반환한다.", example = "waiting")
            @RequestParam(required = false) String status) {
        return reservationService.findByRoom(roomNumber, status);
    }
}
