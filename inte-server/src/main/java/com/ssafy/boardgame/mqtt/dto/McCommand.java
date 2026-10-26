package com.ssafy.boardgame.mqtt.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * 세션만 지목하면 되는 진행자 명령의 페이로드
 * (/room/{roomNumber}/mc/cmd/analyze, finish, abort).
 * <p>
 * 시작 명령만 게임 코드가 더 필요해서 {@link McStart} 로 따로 둔다.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class McCommand {
    /** mc/cmd/start 로 내려보낸 게임 세션 식별자 */
    private String sessionId;
}
