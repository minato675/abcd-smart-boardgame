package com.ssafy.boardgame.common;

import lombok.Getter;
import org.springframework.http.HttpStatus;

/**
 * 서비스 전역에서 사용하는 에러 코드.
 * 응답 본문에는 code/message 가, 응답 상태에는 status 가 사용된다.
 */
@Getter
public enum ErrorCode {

    // 404
    BOARD_GAME_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 보드게임입니다."),
    ROOM_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 방 번호입니다."),
    RESERVATION_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 예약입니다."),
    RFID_NOT_REGISTERED(HttpStatus.NOT_FOUND, "등록되지 않은 카드입니다."),
    CABINET_NOT_FOUND(HttpStatus.NOT_FOUND, "열어야 할 사물함이 없습니다."),

    // 403
    RESERVATION_FORBIDDEN(HttpStatus.FORBIDDEN, "해당 예약을 취소할 권한이 없습니다."),

    // 409
    BOARD_GAME_OUT_OF_STOCK(HttpStatus.CONFLICT, "대여 가능한 보드게임이 없습니다. 예약해 주세요."),
    ALREADY_RENTED(HttpStatus.CONFLICT, "이미 해당 보드게임을 대여 중입니다."),
    DUPLICATE_RESERVATION(HttpStatus.CONFLICT, "이미 예약 대기 중인 보드게임이 있습니다."),
    RESERVATION_NOT_NEEDED(HttpStatus.CONFLICT, "지금 바로 대여할 수 있습니다."),
    RESERVATION_NOT_CANCELABLE(HttpStatus.CONFLICT, "대기 중인 예약만 취소할 수 있습니다."),
    ROOM_NOT_IN_USE(HttpStatus.CONFLICT, "이용 중인 방이 아닙니다. 입실 처리 후 이용해 주세요."),
    NO_ACTIVE_RENT(HttpStatus.CONFLICT, "대여 중인 보드게임이 없습니다."),
    MC_SESSION_NOT_FOUND(HttpStatus.CONFLICT, "진행 중인 AI 심판이 없습니다."),

    // 400
    INVALID_INPUT(HttpStatus.BAD_REQUEST, "요청 값이 올바르지 않습니다."),
    INVALID_PLAYER_RANGE(HttpStatus.BAD_REQUEST, "최소 인원이 최대 인원보다 클 수 없습니다."),
    INVALID_PLAYER_COUNT(HttpStatus.BAD_REQUEST, "이 게임에서 진행할 수 없는 인원입니다."),
    CATEGORY_NOT_FOUND(HttpStatus.BAD_REQUEST, "존재하지 않는 카테고리가 포함되어 있습니다."),
    INVALID_IMAGE_TYPE(HttpStatus.BAD_REQUEST, "이미지는 jpg, jpeg, png, webp, gif 형식만 업로드할 수 있습니다."),

    // 413
    IMAGE_TOO_LARGE(HttpStatus.CONTENT_TOO_LARGE, "이미지 용량이 허용 범위를 초과했습니다."),

    // 500
    IMAGE_UPLOAD_FAILED(HttpStatus.INTERNAL_SERVER_ERROR, "이미지 저장에 실패했습니다."),
    INTERNAL_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "서버 오류가 발생했습니다.");

    private final HttpStatus status;
    private final String message;

    ErrorCode(HttpStatus status, String message) {
        this.status = status;
        this.message = message;
    }
}
