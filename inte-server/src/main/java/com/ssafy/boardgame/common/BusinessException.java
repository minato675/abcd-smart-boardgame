package com.ssafy.boardgame.common;

import lombok.Getter;

/**
 * 비즈니스 규칙 위반을 나타내는 예외.
 * GlobalExceptionHandler 가 ErrorCode 의 상태코드/메시지로 변환한다.
 */
@Getter
public class BusinessException extends RuntimeException {

    private final ErrorCode errorCode;

    public BusinessException(ErrorCode errorCode) {
        super(errorCode.getMessage());
        this.errorCode = errorCode;
    }

    public BusinessException(ErrorCode errorCode, String message) {
        super(message);
        this.errorCode = errorCode;
    }
}
