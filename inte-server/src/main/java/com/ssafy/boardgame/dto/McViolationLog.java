package com.ssafy.boardgame.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * 규칙 위반 한 건 (mc_violation_log 테이블).
 *
 * @see com.ssafy.boardgame.mapper.McViolationLogMapper
 */
@Getter
@Setter
@NoArgsConstructor
public class McViolationLog {

    private Long violationLogId;
    private String sessionId;
    private String roomNumber;
    /** 어떤 게임에서 나온 위반인지. 세션을 특정하지 못하면 null 이다. */
    private Long boardGameId;
    /** 고정 위반 코드 */
    private String code;
    /** 태블릿에 표시된 문구 */
    private String message;
    private LocalDateTime createdAt;
    private String table;
}
