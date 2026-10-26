package com.ssafy.boardgame.mqtt.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * AI 심판 시작 명령 페이로드 (/room/{roomNumber}/mc/cmd/start).
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class McStart {
    /** 게임 세션 식별자(UUID). 이후 mc/event/* 로 올라오는 이벤트를 이 값으로 한 판에 묶는다. */
    private String sessionId;
    /** 서버와 진행자가 합의한 게임 코드 */
    private String boardGameName;
    /**
     * 이 판을 하는 사람 수. 좌석 번호는 1..playerCount 이고 판이 끝날 때까지 바뀌지 않는다.
     * <p>
     * 진행자가 좌석별 상태(루미큐브라면 첫 등록 30점을 마쳤는지)를 들고 있으려면
     * 배열 크기를 알아야 하는데, 카메라는 테이블만 보므로 스스로 셀 수 없다.
     * 사람 수를 아는 곳은 태블릿뿐이라 시작 명령에 실어 내려보낸다.
     */
    private int playerCount;
}
