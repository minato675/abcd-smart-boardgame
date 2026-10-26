package com.ssafy.boardgame.common;

import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindException;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

import java.util.stream.Collectors;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ErrorResponse> handleBusiness(BusinessException e) {
        log.warn("비즈니스 예외: {} - {}", e.getErrorCode(), e.getMessage());
        return ResponseEntity.status(e.getErrorCode().getStatus())
                .body(ErrorResponse.of(e.getErrorCode(), e.getMessage()));
    }

    /**
     * @Valid @RequestBody 검증 실패. 어떤 필드가 왜 틀렸는지 메시지에 담아 준다.
     */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException e) {
        return invalidInput(e.getBindingResult());
    }

    /**
     * @Valid @ModelAttribute 검증/바인딩 실패. multipart 폼(보드게임 등록)이 이 경로를 탄다.
     */
    @ExceptionHandler(BindException.class)
    public ResponseEntity<ErrorResponse> handleBind(BindException e) {
        return invalidInput(e.getBindingResult());
    }

    /**
     * spring.servlet.multipart 제한 초과. 파일 크기 제한은 바인딩 전에 걸리므로 여기서 받는다.
     */
    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ErrorResponse> handleMaxUploadSize(MaxUploadSizeExceededException e) {
        log.warn("업로드 용량 초과: {}", e.getMessage());
        return ResponseEntity.status(ErrorCode.IMAGE_TOO_LARGE.getStatus())
                .body(ErrorResponse.of(ErrorCode.IMAGE_TOO_LARGE));
    }

    /**
     * uq_reservation_waiting_room 부분 유니크 인덱스 위반
     * = 동시 요청으로 한 방에 대기 예약이 2건 생기려는 경우.
     */
    @ExceptionHandler(DuplicateKeyException.class)
    public ResponseEntity<ErrorResponse> handleDuplicateKey(DuplicateKeyException e) {
        log.warn("유니크 제약 위반: {}", e.getMessage());
        return ResponseEntity.status(ErrorCode.DUPLICATE_RESERVATION.getStatus())
                .body(ErrorResponse.of(ErrorCode.DUPLICATE_RESERVATION));
    }

    private ResponseEntity<ErrorResponse> invalidInput(BindingResult bindingResult) {
        String message = bindingResult.getFieldErrors().stream()
                .map(this::formatFieldError)
                .collect(Collectors.joining(", "));
        return ResponseEntity.status(ErrorCode.INVALID_INPUT.getStatus())
                .body(ErrorResponse.of(ErrorCode.INVALID_INPUT, message));
    }

    private String formatFieldError(FieldError error) {
        return error.getField() + ": " + error.getDefaultMessage();
    }
}
