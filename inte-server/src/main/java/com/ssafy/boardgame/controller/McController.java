package com.ssafy.boardgame.controller;

import com.ssafy.boardgame.common.ErrorResponse;
import com.ssafy.boardgame.dto.McSessionResponse;
import com.ssafy.boardgame.dto.McStartResponse;
import com.ssafy.boardgame.dto.McTurnLogResponse;
import com.ssafy.boardgame.dto.McTurnResponse;
import com.ssafy.boardgame.service.McService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Slf4j
@RestController
@RequestMapping("/mc")
@RequiredArgsConstructor
@Tag(name = "AI 심판", description = "진행자(AI 심판) 세션 제어")
public class McController {

    private final McService mcService;

    /** 태블릿의 AI 심판 버튼 */
    @Operation(summary = "AI 심판 시작",
            description = """
                    /room/{roomNumber}/mc/cmd/start 로 진행자 시작 명령을 발행한다.
                    보드게임은 방이 대여 중인 것에서 서버가 고르고, sessionId 는 서버가 발급해 응답으로 돌려준다.
                    이후 /room/{roomNumber}/mc/event/turn-log 와 mc/event/violation 을 이 값으로 한 판에 묶는다.

                    playerCount 는 태블릿이 물어봐서 보낸다. 카메라는 테이블만 보므로 몇 명인지 셀 수 없는데,
                    루미큐브 첫 등록 30점처럼 사람마다 갈리는 규칙을 판정하려면 진행자가 좌석 수를 알아야 한다.
                    이미 켜져 있으면 요청한 인원은 무시하고 진행 중인 세션을 그대로 돌려준다.
                    """)
    @ApiResponse(responseCode = "200", description = "AI 심판 시작 명령 발행 성공")
    @ApiResponse(responseCode = "400", description = "INVALID_PLAYER_COUNT - 이 게임의 인원 범위 밖",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @ApiResponse(responseCode = "409", description = "NO_ACTIVE_RENT - 대여 중인 게임이 없음",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @PostMapping("/start")
    public McStartResponse start(
            @Parameter(description = "방 번호", example = "A1", required = true)
            @RequestParam String roomNumber,
            @Parameter(description = "이 판을 하는 사람 수", example = "4", required = true)
            @RequestParam int playerCount) {
        return mcService.start(roomNumber, playerCount);
    }

    /** 태블릿의 턴 넘기기 버튼 */
    @Operation(summary = "턴 넘기기(분석 지시)",
            description = """
                    /room/{roomNumber}/mc/cmd/analyze 로 분석 지시를 발행한다.
                    sessionId 와 방금 차례를 마친 seat 은 서버가 들고 있는 값을 싣는다.
                    분석 결과는 /room/{roomNumber}/mc/event/turn-log 로 올라온다.

                    차례는 이 호출로 넘어간다(진행자 응답을 기다리지 않는다).
                    응답의 currentSeat 이 다음 차례이므로 태블릿은 좌석 회전을 따로 계산하지 않는다.
                    """)
    @ApiResponse(responseCode = "200", description = "분석 지시 발행 성공")
    @ApiResponse(responseCode = "409", description = "MC_SESSION_NOT_FOUND - 진행 중인 AI 심판이 없음",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @PostMapping("/analyze")
    public McTurnResponse analyze(
            @Parameter(description = "방 번호", example = "A1", required = true)
            @RequestParam String roomNumber) {
        return mcService.analyze(roomNumber);
    }

    /** 태블릿의 '다 냈어요' 버튼 */
    @Operation(summary = "지금 차례인 사람이 손패를 다 냄",
            description = """
                    그 좌석을 차례 회전에서 빼고 다음 사람에게 넘긴다. 카메라는 손패를 못 보므로
                    누가 끝났는지는 이 호출로만 알 수 있다.

                    진행자에게 따로 보내는 명령은 없다 - 끝난 좌석으로 analyze 를 더 보내지 않는 것으로 충분하다.
                    남은 사람이 하나뿐이 되면 세션까지 종료하고(mc/cmd/finish 발행) sessionEnded=true 로 알린다.
                    """)
    @ApiResponse(responseCode = "200", description = "처리 성공")
    @ApiResponse(responseCode = "409", description = "MC_SESSION_NOT_FOUND - 진행 중인 AI 심판이 없음",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @PostMapping("/player-finish")
    public McTurnResponse finishPlayer(
            @Parameter(description = "방 번호", example = "A1", required = true)
            @RequestParam String roomNumber) {
        return mcService.finishPlayer(roomNumber);
    }

    /** 태블릿이 화면을 띄울 때 심판이 도는 중인지 확인 */
    @Operation(summary = "진행 중인 AI 심판 세션 조회",
            description = """
                    이 방에 진행 중인 세션이 있으면 돌려준다. 없으면 본문 없이 200 이다.
                    태블릿이 새로고침된 뒤 심판 패널을 복원하는 데 쓴다 - 이게 없으면 심판이 도는 줄 모르고
                    권유 팝업을 다시 띄우게 되고, 확인하면 판이 둘로 갈린다.
                    """)
    @ApiResponse(responseCode = "200", description = "조회 성공 (진행 중인 세션이 없으면 빈 본문)")
    @GetMapping("/session")
    public McSessionResponse findActiveSession(
            @Parameter(description = "방 번호", example = "A1", required = true)
            @RequestParam String roomNumber) {
        return mcService.findActiveSession(roomNumber);
    }

    /** 태블릿의 이전 화면 보기 버튼 */
    @Operation(summary = "마지막 테이블 상태 조회",
            description = """
                    진행 중인 세션에서 turn_no 가 가장 큰(= 마지막으로 기록된) 테이블 상태를 돌려준다.
                    태블릿이 MQTT 로 받아 들고 있는 값이 아니라 DB 를 읽으므로, 새로고침한 뒤에도 복원된다.
                    아직 기록된 턴이 없으면 본문 없이 200 이다.
                    """)
    @ApiResponse(responseCode = "200", description = "조회 성공 (기록이 없으면 빈 본문)")
    @ApiResponse(responseCode = "409", description = "MC_SESSION_NOT_FOUND - 진행 중인 AI 심판이 없음",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @GetMapping("/turn-log")
    public McTurnLogResponse findLatestTurnLog(
            @Parameter(description = "방 번호", example = "A1", required = true)
            @RequestParam String roomNumber) {
        return mcService.findLatestTurnLog(roomNumber);
    }

    /** 태블릿의 심판 끄기 버튼 */
    @Operation(summary = "AI 심판 종료",
            description = """
                    /room/{roomNumber}/mc/cmd/finish 로 정상 종료 지시를 발행한다.
                    진행 중인 세션이 없어도 200 이다 - 끄는 요청은 이미 꺼져 있으면 목적이 달성된 것이고,
                    여기서 막으면 세션을 잃은 방이 화면의 심판 패널을 닫지 못한다.
                    """)
    @ApiResponse(responseCode = "200", description = "종료 지시 발행 성공 (세션이 없었으면 발행 없이 성공)")
    @PostMapping("/finish")
    public void finish(
            @Parameter(description = "방 번호", example = "A1", required = true)
            @RequestParam String roomNumber) {
        mcService.finish(roomNumber);
    }
}
