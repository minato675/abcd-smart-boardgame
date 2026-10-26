package com.ssafy.boardgame.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * 룰 설명 질의/응답 한 건 (qna_log 테이블).
 *
 * @see com.ssafy.boardgame.mapper.QnaLogMapper
 */
@Getter
@Setter
@NoArgsConstructor
public class QnaLog {

    private Long qnaLogId;
    /** QnA 세션 식별자. 한 세션에서 여러 번 주고받으면 같은 값으로 여러 행이 쌓인다. */
    private String transactionId;
    private String roomNumber;
    /** 어떤 게임의 규칙을 물었는지. 세션을 특정하지 못하면 null 이다. */
    private Long boardGameId;
    /** 사용자 발화 text */
    private String req;
    /** 응답 text */
    private String res;
    private LocalDateTime createdAt;
}
