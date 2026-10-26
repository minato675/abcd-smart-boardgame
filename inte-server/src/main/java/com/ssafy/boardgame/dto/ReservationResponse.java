package com.ssafy.boardgame.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * 예약 정보. waitingRank 는 목록/취소 응답에서는 채우지 않는다(null).
 */
@Getter
@Setter
@NoArgsConstructor
public class ReservationResponse {

    private Long reservationId;
    private Long boardGameId;
    private String boardGameName;
    private String roomNumber;
    private String status;
    private LocalDateTime reservedAt;
    private LocalDateTime fulfilledAt;
    private LocalDateTime cancelledAt;

    /** 내 앞에 대기 중인 팀 수 + 1 */
    private Integer waitingRank;
}
