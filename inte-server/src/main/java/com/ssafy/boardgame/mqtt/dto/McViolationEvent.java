package com.ssafy.boardgame.mqtt.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.List;

/**
 * 진행자가 잡아낸 규칙 위반 페이로드 (/room/{roomNumber}/mc/event/violation).
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class McViolationEvent {
    /** mc/cmd/start 로 내려보낸 게임 세션 식별자 */
    private String sessionId;
    /** 고정 위반 코드. 클라이언트 분기와 로그 집계에 쓴다. */
    private String code;
    /** 태블릿에 그대로 표시할 사용자용 문구 */
    private String message;
    /** 잘못 구성된 타일 목록 */
    private List<List<McTile>> table;
}
