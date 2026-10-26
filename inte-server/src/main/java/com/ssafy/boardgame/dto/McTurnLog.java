package com.ssafy.boardgame.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * 진행자가 읽은 테이블 상태 한 건 (mc_turn_log 테이블).
 *
 * @see com.ssafy.boardgame.mapper.McTurnLogMapper
 */
@Getter
@Setter
@NoArgsConstructor
public class McTurnLog {

    private Long turnLogId;
    private String sessionId;
    private String roomNumber;
    /** 이 세션에서 몇 번째 턴인지. 서버가 기존 행을 세어 채운다. */
    private Integer turnNo;
    /** tableState 안 타일 총 개수 */
    private int tileCount;
    /** 테이블 상태 JSON. [[{color,number}, ...], ...] */
    private String tableState;
    private LocalDateTime createdAt;
}
