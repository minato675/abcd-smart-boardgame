package com.ssafy.boardgame.common;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;

/**
 * 실패 응답 본문. 성공 응답은 별도 래퍼 없이 DTO 를 그대로 반환한다.
 */
@Getter
@Schema(description = "실패 응답 본문. 성공 응답은 별도 래퍼 없이 DTO 를 그대로 반환한다.")
public class ErrorResponse {

    @Schema(description = "에러 코드 (ErrorCode enum 이름)", example = "BOARD_GAME_NOT_FOUND")
    private final String code;

    @Schema(description = "사용자에게 보여줄 메시지", example = "존재하지 않는 보드게임입니다.")
    private final String message;

    private ErrorResponse(String code, String message) {
        this.code = code;
        this.message = message;
    }

    public static ErrorResponse of(ErrorCode errorCode) {
        return new ErrorResponse(errorCode.name(), errorCode.getMessage());
    }

    public static ErrorResponse of(ErrorCode errorCode, String message) {
        return new ErrorResponse(errorCode.name(), message);
    }
}
