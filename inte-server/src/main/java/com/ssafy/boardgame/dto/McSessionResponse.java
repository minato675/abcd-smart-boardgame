package com.ssafy.boardgame.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.List;

/**
 * 진행 중인 AI 심판 세션.
 * <p>
 * 태블릿이 새로고침된 뒤 화면을 복원하는 근거다. sessionId 를 태블릿이 보관하면
 * 새로고침에 잃고, localStorage 에 넣어도 서버가 재배포되면 죽은 값을 들고 있게 되므로
 * 매번 서버에 묻는다.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "진행 중인 AI 심판 세션")
public class McSessionResponse {

    @Schema(description = "게임 세션 식별자", example = "123e4567-e89b-12d3-a456-556642440000")
    private String sessionId;

    @Schema(description = "심판이 진행 중인 보드게임명", example = "루미큐브")
    private String boardGameName;

    @Schema(description = "지금까지 기록된 마지막 턴 번호. 아직 없으면 0.", example = "3")
    private int turnNo;

    @Schema(description = "이 판을 하는 사람 수", example = "4")
    private int playerCount;

    /**
     * 이게 없으면 새로고침한 태블릿이 누구 차례인지 몰라 좌석 표시가 1번으로 돌아간다.
     * 서버는 계속 제 좌석으로 진행자에게 지시를 보내므로 화면만 어긋난다.
     */
    @Schema(description = "지금 차례인 좌석", example = "2")
    private int currentSeat;

    @Schema(description = "손패를 다 낸 좌석 (완료 순서)", example = "[3]")
    private List<Integer> finishedSeats;
}
