package com.ssafy.boardgame.mqtt.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * QnA 질의/응답 결과 페이로드 (/room/{roomNumber}/qna/res).
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class QnaRes {
    /** QnA 세션 식별자. qna/start 로 내려보낸 값이 그대로 돌아온다. */
    private String transactionId;
    /** 사용자 발화 text */
    private String req;
    /** 응답 text */
    private String res;
}
