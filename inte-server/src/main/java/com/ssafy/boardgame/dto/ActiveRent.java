package com.ssafy.boardgame.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * 방에서 아직 끝나지 않은 대여 한 건 (서비스 내부용).
 * <p>
 * status 가 USING 이면 이번 개폐는 반납, RENT 면 픽업이다.
 * 반납일 때 사본을 재고로 되돌려야 해서 boardGameItemId 도 함께 가져온다.
 */
@Getter
@Setter
@NoArgsConstructor
public class ActiveRent {

    private Long rentId;
    private String status;
    /** 반납이 확정된 뒤 이 게임을 기다리던 예약자에게 알림을 보내는 데 쓴다. */
    private Long boardGameId;
    private Long boardGameItemId;
}
