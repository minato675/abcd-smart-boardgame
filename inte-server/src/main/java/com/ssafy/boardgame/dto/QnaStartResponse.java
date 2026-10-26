package com.ssafy.boardgame.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * 룰 설명(QnA) 시작 응답.
 * <p>
 * transactionId 는 서버가 발급한다. 이후 /room/{roomNumber}/qna/res 로 올라오는 로그를
 * 이 값으로 한 세션에 묶기 위해 태블릿에도 돌려준다.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "룰 설명(QnA) 시작 응답")
public class QnaStartResponse {

    @Schema(description = "서버가 발급한 QnA 세션 식별자",
            example = "123e4567-e89b-12d3-a456-556642440000")
    private String transactionId;

    @Schema(description = "룰 설명을 시작한 방 번호", example = "A1")
    private String roomNumber;
}
