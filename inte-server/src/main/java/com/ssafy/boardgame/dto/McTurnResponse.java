package com.ssafy.boardgame.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * 차례가 한 번 넘어간 결과 (턴 넘기기 / 다 냈어요 공통).
 * <p>
 * 좌석 회전을 태블릿이 따라 계산하지 않게 하려고 서버가 결과를 돌려준다.
 * 양쪽에서 같은 규칙(끝난 사람 건너뛰기, 마지막 한 명이면 종료)을 구현하면
 * 언젠가 어긋나고, 그때 진행자에게 가는 seat 과 화면에 보이는 좌석이 달라진다.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "차례가 넘어간 결과")
public class McTurnResponse {

    @Schema(description = "방금 차례를 마친 좌석", example = "2")
    private int seat;

    @Schema(description = "다음 차례 좌석. 세션이 끝났으면 0", example = "3")
    private int currentSeat;

    @Schema(description = "아직 손패를 다 내지 않은 인원", example = "3")
    private int remainingPlayers;

    @Schema(description = "남은 사람이 하나뿐이라 세션까지 끝났는지", example = "false")
    private boolean sessionEnded;
}
