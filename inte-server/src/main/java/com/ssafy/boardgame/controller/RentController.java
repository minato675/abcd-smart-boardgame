package com.ssafy.boardgame.controller;

import com.ssafy.boardgame.common.ErrorResponse;
import com.ssafy.boardgame.dto.ActiveRentResponse;
import com.ssafy.boardgame.dto.RentRequest;
import com.ssafy.boardgame.dto.RentResponse;
import com.ssafy.boardgame.service.RentService;
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
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@Slf4j
@RestController
@RequestMapping("/rent")
@RequiredArgsConstructor
@Tag(name = "대여", description = "보드게임 대여 및 대여 중 목록 조회")
public class RentController {

    private final RentService rentService;

    /** 보드게임 대여하기 */
    @Operation(summary = "보드게임 대여",
            description = "재고가 있으면 대여를 생성하고 해당 사물함을 연다. 재고가 없으면 409 로 예약을 안내한다.")
    @ApiResponse(responseCode = "201", description = "대여 생성 성공")
    @ApiResponse(responseCode = "400", description = "INVALID_INPUT - 요청 값 검증 실패",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @ApiResponse(responseCode = "404", description = "BOARD_GAME_NOT_FOUND / ROOM_NOT_FOUND / CABINET_NOT_FOUND",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @ApiResponse(responseCode = "409",
            description = "BOARD_GAME_OUT_OF_STOCK - 재고 없음 / ALREADY_RENTED - 이미 대여 중 / ROOM_NOT_IN_USE - 입실하지 않은 방",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public RentResponse rent(@Valid @RequestBody RentRequest request) {
        return rentService.rent(request);
    }

    /**
     * 방이 아직 반납하지 않은 대여 목록 (태블릿이 '사용 중 / 꺼내기 대기' 를 구분하는 근거).
     * status 는 카드 태그로만 바뀌므로 태블릿은 이 조회로만 픽업 여부를 알 수 있다.
     */
    @Operation(summary = "방별 대여 중 목록 조회",
            description = """
                    아직 반납하지 않은 대여 목록을 반환한다.
                    status 는 카드 태그 시점에만 바뀌므로, 태블릿은 이 조회로 '사용 중 / 꺼내기 대기' 를 구분한다.
                    """)
    @ApiResponse(responseCode = "200", description = "조회 성공 (대여 중인 건이 없으면 빈 배열)")
    @GetMapping
    public List<ActiveRentResponse> findActiveRents(
            @Parameter(description = "방 번호", example = "A1", required = true)
            @RequestParam String roomNumber) {
        return rentService.findActiveRents(roomNumber);
    }
}
