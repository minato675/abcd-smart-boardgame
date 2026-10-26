package com.ssafy.boardgame.controller;

import com.ssafy.boardgame.common.ErrorResponse;
import com.ssafy.boardgame.dto.BoardGameDetailResponse;
import com.ssafy.boardgame.dto.BoardGameListResponse;
import com.ssafy.boardgame.dto.BoardGameSearchCondition;
import com.ssafy.boardgame.service.BoardGameService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@Slf4j
@RestController
@RequestMapping("/boardgame")
@RequiredArgsConstructor
@Tag(name = "보드게임", description = "보드게임 목록 조회 및 상세 조회")
public class BoardGameController {

    private final BoardGameService boardGameService;

    /**
     * 보드게임 전체검색 / 조건검색.
     * 파라미터를 하나도 주지 않으면 전체 목록이므로 엔드포인트를 나누지 않는다.
     * 예) GET /api/board-games?keyword=루미&categoryId=1&players=4
     */
    @Operation(summary = "보드게임 목록 조회 / 조건 검색",
            description = "파라미터를 하나도 주지 않으면 전체 목록을 반환한다. 조건은 AND 로 결합된다.")
    @ApiResponse(responseCode = "200", description = "조회 성공 (조건에 맞는 게임이 없으면 빈 배열)")
    @GetMapping
    public List<BoardGameListResponse> search(@ModelAttribute BoardGameSearchCondition condition) {
        return boardGameService.search(condition);
    }

    /** 보드게임 상세정보 */
    @Operation(summary = "보드게임 상세 조회",
            description = "보드게임 단건의 상세 정보와 보유/대여 현황을 반환한다.")
    @ApiResponse(responseCode = "200", description = "조회 성공")
    @ApiResponse(responseCode = "404", description = "BOARD_GAME_NOT_FOUND - 존재하지 않는 보드게임",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @GetMapping("/{boardGameId}")
    public BoardGameDetailResponse detail(
            @Parameter(description = "보드게임 ID", example = "1", required = true)
            @PathVariable Long boardGameId) {
        return boardGameService.findDetail(boardGameId);
    }
}
