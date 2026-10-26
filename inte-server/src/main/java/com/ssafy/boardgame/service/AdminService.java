package com.ssafy.boardgame.service;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.dto.RoomRequest;
import com.ssafy.boardgame.dto.RoomResponse;
import com.ssafy.boardgame.dto.RoomUsageRequest;
import com.ssafy.boardgame.dto.RoomUsageResponse;
import com.ssafy.boardgame.mapper.BoardGameItemMapper;
import com.ssafy.boardgame.mapper.RentMapper;
import com.ssafy.boardgame.mapper.ReservationMapper;
import com.ssafy.boardgame.mapper.RoomMapper;
import com.ssafy.boardgame.mapper.RoomUsageMapper;
import com.ssafy.boardgame.mqtt.MqttPublisher;
import com.ssafy.boardgame.util.StatusUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Locale;

@Slf4j
@Service
@RequiredArgsConstructor
public class AdminService {
    private final RoomMapper roomMapper;
    private final RoomUsageMapper roomUsageMapper;
    private final RentMapper rentMapper;
    private final BoardGameItemMapper boardGameItemMapper;
    private final ReservationMapper reservationMapper;
    private final ReservationNotifyService reservationNotifyService;
    private final MqttPublisher mqttPublisher;
    /**
     * 룸 상태변경(사용/퇴실).
     * 퇴실로 바꾸는 경우에만 그 방이 남긴 대여/예약을 함께 정리한다.
     * 상태 변경과 정리가 한 트랜잭션이어야 '방은 비었는데 사본은 RENTED' 같은 중간 상태가 남지 않는다.
     *
     * 주의: 이 메서드는 room.status 만 바꾸고 room_usage 는 건드리지 않는다.
     * 이용 이력까지 남기려면 checkIn/checkOut 을 쓸 것. 이 경로로 USE/EMPTY 를 보내면
     * 이용 이력과 방 상태가 어긋난다(예: 방은 EMPTY 인데 end_time 이 열린 채 남음).
     */
    @Transactional
    public RoomResponse updateRoomStatus(RoomRequest roomRequest) {
        String roomNumber = roomRequest.getRoomNumber();
        String status = toRoomStatus(roomRequest.getStatus());

        RoomResponse room = roomMapper.findByRoomNumber(roomNumber);
        if (room == null) { //방이 없을 때
            throw new BusinessException(ErrorCode.ROOM_NOT_FOUND);
        }

        //상태 변경
        roomMapper.updateRoomStatus(roomNumber, status);

        //퇴실일 때만 대여/예약 정리
        if (StatusUtil.STATUS_ROOM_EMPTY.equals(status)) {
            cleanUpRoom(roomNumber);
        }

        return roomMapper.findByRoomNumber(roomNumber);
    }

    /**
     * 입실. room_usage 에 이용 이력을 남기고 방을 USE 로 바꾼다.
     *
     * 이미 이용 중인 방에 다시 요청이 와도 열린 이용건을 그대로 두고 insert 만 건너뛴다(멱등).
     * 센서/컨트롤러 재전송으로 같은 입실이 두 번 들어와도 이용 이력이 쪼개지지 않는다.
     */
    @Transactional
    public RoomUsageResponse checkIn(RoomUsageRequest request) {
        String roomNumber = request.getRoomNumber();
        requireRoom(roomNumber);

        int inserted = roomUsageMapper.insertIfAbsent(roomNumber);
        roomMapper.updateRoomStatus(roomNumber, StatusUtil.STATUS_ROOM_USE);

        //wake word start
        mqttPublisher.wakeStartListen(roomNumber);

        log.info("입실 - room={}, 이용이력 신규생성={}", roomNumber, inserted == 1);

        return withRoomStatus(roomUsageMapper.findOpenByRoom(roomNumber),
                roomNumber, StatusUtil.STATUS_ROOM_USE);
    }

    /**
     * 퇴실. 이용 이력의 end_time 을 닫고 방을 EMPTY 로 바꾼 뒤 그 방이 남긴 대여/예약을 정리한다.
     *
     * 정리(cleanUpRoom)까지 하는 이유: 여기서 빼면 이 API 로 퇴실한 방의 사본이 RENTED 로 남아
     * 영구히 대여 불가가 된다. updateRoomStatus 의 EMPTY 경로와 같은 마감 처리를 재사용한다.
     */
    @Transactional
    public RoomUsageResponse checkOut(RoomUsageRequest request) {
        String roomNumber = request.getRoomNumber();
        requireRoom(roomNumber);

        int closed = roomUsageMapper.closeByRoom(roomNumber);
        roomMapper.updateRoomStatus(roomNumber, StatusUtil.STATUS_ROOM_EMPTY);
        cleanUpRoom(roomNumber);

        //wake word stop
        mqttPublisher.wakeStopListen(roomNumber);

        log.info("퇴실 - room={}, 이용이력 마감={}건", roomNumber, closed);

        return withRoomStatus(roomUsageMapper.findLatestByRoom(roomNumber),
                roomNumber, StatusUtil.STATUS_ROOM_EMPTY);
    }

    /**
     * 조회용. 입실 여부와 무관하게 이 방의 가장 최근 이용 이력(room_usage)을 돌려준다.
     * 손님 화면 헤더가 이용 시간을 표시할 때 쓴다 — 태블릿 가동 시간이 아니라
     * 실제 입실 시각(startTime) 기준으로 경과 시간을 계산하기 위함이다.
     *
     * 이용 이력이 한 건도 없으면 usage 는 null 이고(withRoomStatus 가 방 상태만 채운다),
     * 이때 startTime 도 null 이므로 화면은 00:00:00 으로 둔다.
     */
    public RoomUsageResponse getLatestUsage(String roomNumber) {
        RoomResponse room = requireRoom(roomNumber);
        return withRoomStatus(roomUsageMapper.findLatestByRoom(roomNumber), roomNumber, room.getStatus());
    }

    /**
     * 요청의 상태값을 room.status 에 저장할 표기(StatusUtil 의 소문자 상수)로 맞춘다.
     *
     * API 는 대문자 EMPTY/USE 만 받지만(RoomRequest 의 @Pattern) 저장·비교는 전부 소문자다.
     * 요청 값을 그대로 저장하면 두 곳이 깨진다.
     * 1) 아래 퇴실 분기(STATUS_ROOM_EMPTY.equals)가 성립하지 않아 대여/예약 정리가 통째로 누락된다.
     * 2) RentService/ReservationService 의 '이용 중' 판정이 STATUS_ROOM_USE 와 비교하므로,
     *    이 API 로 USE 로 바꾼 방은 대여·예약이 전부 ROOM_NOT_IN_USE 로 거부된다.
     *
     * 이미 소문자로 들어온 값은 그대로 통과하므로(멱등) 서비스를 직접 호출하는 경로에도 안전하다.
     */
    private String toRoomStatus(String requestStatus) {
        return requestStatus == null ? null : requestStatus.toLowerCase(Locale.ROOT);
    }

    private RoomResponse requireRoom(String roomNumber) {
        RoomResponse room = roomMapper.findByRoomNumber(roomNumber);
        if (room == null) {
            throw new BusinessException(ErrorCode.ROOM_NOT_FOUND);
        }
        return room;
    }

    /**
     * 이용 이력이 아직 한 건도 없는 방에 퇴실만 들어오는 경우가 있어(입실 누락) usage 가 null 일 수 있다.
     * 그때도 응답을 null 로 내리지 않고 방 상태만이라도 채워 준다.
     */
    private RoomUsageResponse withRoomStatus(RoomUsageResponse usage, String roomNumber, String roomStatus) {
        RoomUsageResponse response = (usage != null) ? usage : new RoomUsageResponse();
        response.setRoomNumber(roomNumber);
        response.setRoomStatus(roomStatus);
        return response;
    }

    /**
     * 퇴실 정리. 손님이 반납/예약취소를 누르지 않고 나가는 경우가 있어 방 단위로 한 번에 마감한다.
     *
     * 세 쿼리 모두 대상 조건(returned_at IS NULL / status = 'WAITING')을 UPDATE 안에 들고 있어
     * 이미 EMPTY 인 방에 같은 요청이 다시 와도 0건 처리된다. 즉 재호출해도 안전하고,
     * 상태 갱신이 누락돼 엉킨 방을 관리자가 강제로 정리하는 용도로도 그대로 쓸 수 있다.
     */
    private void cleanUpRoom(String roomNumber) {
        //알림 대상은 마감 전에 뽑아 둔다. returnAllByRoom 이 지나가면 찾을 조건이 사라진다.
        List<Long> returningGames = rentMapper.findActiveBoardGameIds(roomNumber);

        //사본 반납이 먼저다. rent 를 먼저 마감하면 반납할 사본을 찾는 조건이 사라져 RENTED 로 묶인다.
        int released = boardGameItemMapper.releaseByRoom(roomNumber);
        int returned = rentMapper.returnAllByRoom(roomNumber);
        int cancelled = reservationMapper.cancelAllByRoom(roomNumber);

        log.info("퇴실 정리 - room={}, 반납={}건(사본 {}개 복귀), 예약취소={}건",
                roomNumber, returned, released, cancelled);

        //퇴실로 풀린 사본도 기다리는 방에게는 똑같은 반납이다. 여기서 빠지면 손님이 반납을 누르지 않고
        //나간 경우 대기자는 그 게임이 다시 대여됐다 반납될 때까지 알림을 못 받는다.
        //이 방의 대기 예약은 바로 위에서 취소됐으므로 자기 자신에게 알림이 가지 않는다.
        returningGames.forEach(reservationNotifyService::notifyFirstWaiting);
    }
}
