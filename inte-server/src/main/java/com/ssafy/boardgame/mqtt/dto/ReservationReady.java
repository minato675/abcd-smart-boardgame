package com.ssafy.boardgame.mqtt.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * /room/{roomNumber}/reservation/ready 페이로드.
 * <p>
 * 예약한 보드게임이 반납돼 지금 빌릴 수 있다는 알림이다. 태블릿은 이 값으로 팝업을 띄우고,
 * "빌린다" 면 {@code POST /rent}, "안 빌린다" 면 {@code PATCH /reservation/cancel} 로 응답한다.
 * 취소에 필요한 reservationId 를 여기 실어 주므로 태블릿이 따로 조회하지 않아도 된다.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class ReservationReady {

    /** 취소 요청에 그대로 넣을 예약 ID */
    private Long reservationId;
    private Long boardGameId;
    private String boardGameName;
    /**
     * 팝업을 띄워 둘 시간(초).
     * <p>
     * 서버도 같은 시간으로 타이머를 돌려, 응답이 없으면 이 예약을 취소하고 다음 대기자에게 넘긴다.
     * 태블릿은 이 값이 지나면 팝업을 스스로 닫아야 한다 - 이미 남에게 넘어간 팝업이 화면에 남으면
     * "빌린다" 를 눌러도 재고가 없어 409 가 난다.
     */
    private int timeoutSec;
}
