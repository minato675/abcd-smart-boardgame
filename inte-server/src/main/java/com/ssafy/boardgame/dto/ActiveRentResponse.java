package com.ssafy.boardgame.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * 방이 아직 반납하지 않은 대여 한 건 (GET /rent 응답).
 * <p>
 * 태블릿이 "우리 방이 지금 무엇을 들고 있는지" 를 복원하는 용도다. 대여를 만든 것은
 * {@link RentResponse} 지만 그건 생성 시점의 응답이라 status 가 없다 — 픽업/반납은
 * 카드 태그(MQTT)로만 전이되므로 상태는 이 조회로만 알 수 있다.
 *
 * @see com.ssafy.boardgame.service.CabinetService 픽업(RENT->USING) / 반납(USING->RETURNED) 전이
 */
@Getter
@Setter
@NoArgsConstructor
public class ActiveRentResponse {

    private Long rentId;
    private Long boardGameId;
    private String boardGameName;
    private Long boardGameItemId;
    /** 열어야 하는(또는 열었던) 사물함 */
    private Long cabinetId;
    /** 'RENT'(픽업 대기) | 'USING'(사용 중). RETURNED 는 조회 대상이 아니다. */
    private String status;
    private LocalDateTime rentedAt;
}
