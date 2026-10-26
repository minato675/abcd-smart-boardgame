package com.ssafy.boardgame.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * AI 심판 시작 응답.
 * <p>
 * sessionId 는 서버가 발급한다. 이후 /room/{roomNumber}/mc/event/turn-log 와
 * mc/event/violation 을 이 값으로 한 판에 묶기 위해 태블릿에도 돌려준다.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "AI 심판 시작 응답")
public class McStartResponse {

    @Schema(description = "서버가 발급한 게임 세션 식별자",
            example = "123e4567-e89b-12d3-a456-556642440000")
    private String sessionId;

    @Schema(description = "AI 심판이 진행할 보드게임명", example = "루미큐브")
    private String boardGameName;

    @Schema(description = "AI 심판을 시작한 방 번호", example = "A1")
    private String roomNumber;

    /**
     * 요청한 값이 아니라 세션에 실제로 잡힌 값이다 - 이미 켜져 있으면 요청은 무시되고
     * 진행 중인 판의 인원이 그대로 나온다.
     */
    @Schema(description = "이 판을 하는 사람 수", example = "4")
    private int playerCount;

    @Schema(description = "지금 차례인 좌석", example = "1")
    private int currentSeat;
}
