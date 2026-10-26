package com.ssafy.boardgame.service;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.dto.ReservationCancelRequest;
import com.ssafy.boardgame.dto.ReservationRequest;
import com.ssafy.boardgame.dto.ReservationResponse;
import com.ssafy.boardgame.dto.RoomResponse;
import com.ssafy.boardgame.mapper.*;
import com.ssafy.boardgame.util.StatusUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class ReservationService {

    private final BoardGameMapper boardGameMapper;
    private final BoardGameItemMapper boardGameItemMapper;
    private final ReservationMapper reservationMapper;
    private final RentMapper rentMapper;
    private final RoomMapper roomMapper;
    private final ReservationNotifyService reservationNotifyService;

    /**
     * 보드게임 예약하기.
     * reservation 테이블에 시간 슬롯 컬럼이 없으므로 이 예약은 '미래 시점 예약'이 아니라
     * 재고가 없을 때 줄을 서는 대기열이다. 따라서 재고가 남아 있으면 예약 대신 바로 대여하도록 안내한다.
     */
    @Transactional
    public ReservationResponse reserve(ReservationRequest request) {
        Long boardGameId = request.getBoardGameId();
        String roomNumber = request.getRoomNumber();

        // 1. 보드게임 / 방 존재 확인
        String boardGameName = boardGameMapper.findNameById(boardGameId);
        if (boardGameName == null) {
            throw new BusinessException(ErrorCode.BOARD_GAME_NOT_FOUND);
        }
        RoomResponse room = roomMapper.findByRoomNumber(roomNumber);
        if (room == null) { //방이 없을 때
            throw new BusinessException(ErrorCode.ROOM_NOT_FOUND);
        } else if(!room.getStatus().equals(StatusUtil.STATUS_ROOM_USE)) { //방이 사용 중이 아닐 때
            throw new BusinessException(ErrorCode.ROOM_NOT_IN_USE);
        }

        // 2. 이미 그 방이 그 게임을 대여 중이면 예약할 이유가 없다
        if (rentMapper.countActiveRent(roomNumber, boardGameId) > 0) {
            throw new BusinessException(ErrorCode.ALREADY_RENTED);
        }

        // 3. 재고가 남아 있으면 바로 대여 가능
        if (boardGameItemMapper.countAvailable(boardGameId) > 0) {
            throw new BusinessException(ErrorCode.RESERVATION_NOT_NEEDED);
        }

        // 4. 한 방은 대기 예약을 1건만 걸 수 있다. 어떤 게임이든 이미 대기 중이면 거절한다.
        //    (동시 요청은 uq_reservation_waiting_room 부분 유니크 인덱스가 막고
        //     GlobalExceptionHandler 가 DuplicateKeyException 을 409 로 변환한다)
        List<ReservationResponse> waiting = reservationMapper.findByRoom(roomNumber, StatusUtil.STATUS_RESERVATION_WAITING);
        if (waiting != null && !waiting.isEmpty()) {
            throw new BusinessException(ErrorCode.DUPLICATE_RESERVATION);
        }

        // 5. 예약 등록
        ReservationResponse response = new ReservationResponse();
        response.setBoardGameId(boardGameId);
        response.setRoomNumber(roomNumber);
        reservationMapper.insert(response);

        response.setBoardGameName(boardGameName);
        response.setWaitingRank(
                reservationMapper.countWaitingAhead(response.getReservationId(), boardGameId) + 1);

        log.info("예약 등록 - reservationId={}, room={}, boardGameId={}, rank={}",
                response.getReservationId(), roomNumber, boardGameId, response.getWaitingRank());
        return response;
    }

    /**
     * 예약 취소. 인증이 없으므로 방 번호가 소유 증명 역할을 한다.
     */
    @Transactional
    public ReservationResponse cancel(ReservationCancelRequest request) {
        Long reservationId = request.getReservationId();
        ReservationResponse reservation = reservationMapper.findById(reservationId);
        if (reservation == null) {
            throw new BusinessException(ErrorCode.RESERVATION_NOT_FOUND);
        }
        if (!reservation.getRoomNumber().equals(request.getRoomNumber())) {
            throw new BusinessException(ErrorCode.RESERVATION_FORBIDDEN);
        }

        // WAITING 인 경우에만 갱신된다. 0건이면 이미 취소/이행된 예약.
        if (reservationMapper.cancel(reservationId) == 0) {
            throw new BusinessException(ErrorCode.RESERVATION_NOT_CANCELABLE);
        }

        log.info("예약 취소 - reservationId={}, room={}", reservationId, request.getRoomNumber());

        // 반납 알림 팝업의 '안 빌린다' 도 이 경로로 온다. 기다리던 응답이 왔으니 팝업을 놓아 주고,
        // 비워진 자리를 바로 다음 대기자에게 넘긴다. 팝업과 무관한 평범한 취소라면 그 게임은
        // 재고가 없는 상태이므로 notifyFirstWaiting 이 재고 확인에서 조용히 끝난다.
        reservationNotifyService.resolve(reservation.getBoardGameId(), reservation.getRoomNumber());
        reservationNotifyService.notifyFirstWaiting(reservation.getBoardGameId());

        return reservationMapper.findById(reservationId);
    }

    /** 방별 예약 목록. status 를 주지 않으면 전체 상태를 반환한다. */
    @Transactional(readOnly = true)
    public List<ReservationResponse> findByRoom(String roomNumber, String status) {
        return reservationMapper.findByRoom(roomNumber, status);
    }
}
