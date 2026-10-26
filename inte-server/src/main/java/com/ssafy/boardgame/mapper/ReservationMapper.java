package com.ssafy.boardgame.mapper;

import com.ssafy.boardgame.dto.ReservationResponse;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface ReservationMapper {

    /** 성공 시 파라미터 객체의 reservationId/reservedAt/status 가 채워진다. */
    int insert(ReservationResponse reservation);

    ReservationResponse findById(@Param("reservationId") Long reservationId);

    List<ReservationResponse> findByRoom(@Param("roomNumber") String roomNumber,
                                         @Param("status") String status);

    /**
     * 그 게임을 가장 먼저 예약한 대기 건. 없으면 null.
     * <p>
     * 반납 알림은 이 한 건에게만 간다. countWaitingAhead 가 세는 것과 같은 순서(reserved_at)를
     * 써야 손님에게 보여 준 대기 순번 1번과 실제로 알림을 받는 방이 일치한다.
     */
    ReservationResponse findFirstWaiting(@Param("boardGameId") Long boardGameId);

    /** 나보다 먼저 신청한 WAITING 건수 (대기 순번 = 이 값 + 1) */
    int countWaitingAhead(@Param("reservationId") Long reservationId,
                          @Param("boardGameId") Long boardGameId);

    /** WAITING 인 경우에만 취소된다. 반환 0 이면 이미 취소/이행된 예약. */
    int cancel(@Param("reservationId") Long reservationId);

    /** 해당 방의 해당 게임 대기 예약을 이행 처리. 대여 시 호출. */
    int fulfillByRoomAndGame(@Param("roomNumber") String roomNumber,
                             @Param("boardGameId") Long boardGameId);

    /** 퇴실 정리용. 해당 방의 대기 예약을 모두 취소 처리. 이미 이행/취소된 건은 건드리지 않는다. */
    int cancelAllByRoom(@Param("roomNumber") String roomNumber);
}
