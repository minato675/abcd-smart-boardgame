package com.ssafy.boardgame.mqtt.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * 진행자 분석 지시 페이로드 (/room/{roomNumber}/mc/cmd/analyze).
 * <p>
 * 세션만 지목하면 되는 {@link McCommand} 와 달리 좌석이 더 필요하다 - 카메라는
 * 테이블만 보므로 방금 둔 사람이 누구인지 알 수 없는데, 첫 등록 30점처럼 사람마다
 * 다른 규칙을 판정하려면 그 값이 있어야 한다.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class McAnalyze {
    /** mc/cmd/start 로 내려보낸 게임 세션 식별자 */
    private String sessionId;
    /**
     * 방금 차례를 마친 좌석 (1..playerCount).
     * <p>
     * 턴 경계를 아는 곳은 서버뿐이다 - 태블릿의 '턴 넘기기' 가 서버를 거치기 때문이다.
     * 카메라는 손이 지나가는 중간 프레임과 다 둔 상태를 구분할 수 없다.
     */
    private int playerId;
}
