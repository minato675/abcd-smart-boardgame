package com.ssafy.boardgame.mqtt.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * QnA 시작 명령 페이로드 (/room/{roomNumber}/qna/start).
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class QnaStart {
    private String transactionId;
    private String boardGameName;
}
