package com.ssafy.boardgame.service;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.dto.*;
import com.ssafy.boardgame.mapper.BoardGameItemMapper;
import com.ssafy.boardgame.mapper.BoardGameMapper;
import com.ssafy.boardgame.mapper.CabinetMapper;
import com.ssafy.boardgame.mapper.RentMapper;
import com.ssafy.boardgame.mapper.ReservationMapper;
import com.ssafy.boardgame.mapper.RoomMapper;
import com.ssafy.boardgame.mqtt.MqttPublisher;
import com.ssafy.boardgame.mqtt.dto.BoardGameEventType;
import com.ssafy.boardgame.util.StatusUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class RentService {

    private final BoardGameMapper boardGameMapper;
    private final BoardGameItemMapper boardGameItemMapper;
    private final RentMapper rentMapper;
    private final RoomMapper roomMapper;
    private final CabinetMapper cabinetMapper;
    private final ReservationMapper reservationMapper;
    private final MqttPublisher mqttPublisher;
    private final ReservationNotifyService reservationNotifyService;

    @Transactional
    public RentResponse rent(RentRequest request) {
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

        // 2. 같은 방에서 같은 게임을 이미 대여 중이면 거부 (한 방에 같은 게임 2벌은 의미 없음)
        if (rentMapper.countActiveRent(roomNumber, boardGameId) > 0) {
            throw new BusinessException(ErrorCode.ALREADY_RENTED);
        }

        // 3. 대여 가능한 사본 선점 (SKIP LOCKED - 동시 요청 시 서로 다른 사본을 잡거나 재고 없음 처리)
        BoardGameItem item = boardGameItemMapper.findAvailableItemForUpdate(boardGameId);
        if (item == null) {
            throw new BusinessException(ErrorCode.BOARD_GAME_OUT_OF_STOCK);
        }

        // 4. 재고 상태 변경 + 대여 이력 생성 + 이미 대여 이력이 있으면 덮어쓰기
        boardGameItemMapper.updateStatus(item.getItemId(), StatusUtil.STATUS_BOARD_RENTED);

        // 4-1. 아직 받아가지 않은 대여가 있으면 insert 가 그 행을 덮어쓴다(RentMapper.insert 의 UPDATE).
        //      덮어쓰는 순간 그 행이 들고 있던 사본은 rent 어디에서도 참조되지 않게 되는데,
        //      사본을 재고로 되돌리는 두 경로가 모두 rent 를 통해 대상을 찾는다 —
        //      반납 확정(CabinetService)은 rent.board_game_item_id 로, 퇴실 정리
        //      (BoardGameItemMapper.releaseByRoom)는 rent.returned_at IS NULL 로 역추적한다.
        //      그래서 여기서 직접 돌려놓지 않으면 그 사본은 영원히 'rented' 로 남아 재고가 준다.
        Long replacedItemId = rentMapper.findUnpickedItemId(roomNumber);

        RentResponse response = RentResponse.of(boardGameId, boardGameName, item, roomNumber);
        rentMapper.insert(response);

        // insert 이후에 되돌린다. 먼저 돌려놓으면 방금 푼 사본을 같은 트랜잭션의 insert 가
        // 다시 잡을 여지가 생긴다(같은 게임 재대여는 2번에서 이미 막았지만 순서로도 막아 둔다).
        if (replacedItemId != null && !replacedItemId.equals(item.getItemId())) {
            boardGameItemMapper.updateStatus(replacedItemId, StatusUtil.STATUS_BOARD_AVAILABLE);
            log.info("안 받아간 대여를 덮어썼다 - room={}, 재고 복구 itemId={}", roomNumber, replacedItemId);
        }

        // 5. 이 방이 이 게임을 기다리고 있었다면 그 예약은 여기서 끝난다.
        //    남겨 두면 그 방은 부분 유니크 인덱스에 걸려 다음 예약을 못 걸고,
        //    다음 반납 때 이미 빌린 방에게 또 팝업이 뜬다. 줄을 서지 않고 바로 빌린 경우는 0건이다.
        int fulfilled = reservationMapper.fulfillByRoomAndGame(roomNumber, boardGameId);
        // 반납 알림 팝업을 보고 빌린 경우다. 기다리던 응답이 왔으니 타임아웃이 이 예약을 건드리면 안 된다.
        reservationNotifyService.resolve(boardGameId, roomNumber);

        log.info("대여 완료 - rentId={}, room={}, itemId={}, cabinetId={}, 예약이행={}건",
                response.getRentId(), roomNumber, item.getItemId(), item.getCabinetId(), fulfilled);

        // 이 게임의 재고가 줄었다는 걸 모든 방에 알린다 - 남의 방 목록 화면도 이 게임을 보고 있다.
        mqttPublisher.boardGameEvent(BoardGameEventType.RENT, boardGameId, roomNumber);

        return response;
    }

    /**
     * 방이 아직 반납하지 않은 대여 목록.
     * <p>
     * 태블릿을 새로고침해도 '우리 방이 사용 중인 게임' 을 복원하려면 이 조회가 필요하다.
     * 픽업(RENT->USING)과 반납은 카드 태그로만 전이되므로 대여 응답을 클라이언트가
     * 들고 있는 것으로는 실제 상태를 알 수 없다.
     * <p>
     * 방 존재 검증은 하지 않는다 — 조회이고, 없는 방이면 빈 리스트가 맞는 답이다
     * (ReservationService.findByRoom 과 같은 규칙).
     */
    @Transactional(readOnly = true)
    public List<ActiveRentResponse> findActiveRents(String roomNumber) {
        return rentMapper.findActiveRentsByRoom(roomNumber);
    }

    /**
     * 방이 지금 펼쳐 놓고 있는 대여 한 건.
     * <p>
     * findActiveRentsByRoom 은 USING(픽업 완료) 을 RENT(픽업 대기) 보다 먼저,
     * 같은 상태면 최근 대여를 먼저 돌려준다. 카드 태그가 사물함을 고르는 우선순위와
     * 같은 규칙이라, 방금 꺼낸 게임과 여기서 고르는 게임이 어긋나지 않는다.
     * <p>
     * 룰 설명(QnA)과 AI 심판이 "어느 게임인가" 를 이 한 곳에서 판단해야 두 기능이
     * 서로 다른 게임을 집는 일이 없다.
     *
     * @throws BusinessException 대여 중인 게임이 하나도 없는 경우
     */
    @Transactional(readOnly = true)
    public ActiveRentResponse findPlayingRent(String roomNumber) {
        List<ActiveRentResponse> activeRents = rentMapper.findActiveRentsByRoom(roomNumber);
        if (activeRents.isEmpty()) {
            throw new BusinessException(ErrorCode.NO_ACTIVE_RENT);
        }

        ActiveRentResponse target = activeRents.get(0);
        if (activeRents.size() > 1) {
            // 한 방이 여러 게임을 동시에 들고 있을 수 있다. 어느 것을 대상으로 할지는
            // 태블릿만 알지만 지금 요청에는 그 정보가 없어서 위 우선순위로 고른다.
            log.warn("대여 중인 게임이 {}건이라 우선순위로 골랐다 - roomNumber={}, 선택={}, status={}",
                    activeRents.size(), roomNumber, target.getBoardGameName(), target.getStatus());
        }
        return target;
    }

    /**
     * 로그에 남길 보드게임 ID. 대여 중인 게임이 없으면 null.
     * <p>
     * findPlayingRent 와 같은 대상을 고르지만 던지지 않는다 - 통계용 컬럼이라
     * 그 사이 반납했더라도 로그 자체는 남아야 한다.
     */
    @Transactional(readOnly = true)
    public Long findPlayingBoardGameId(String roomNumber) {
        List<ActiveRentResponse> activeRents = rentMapper.findActiveRentsByRoom(roomNumber);
        return activeRents.isEmpty() ? null : activeRents.get(0).getBoardGameId();
    }

    /**
     * 카드키 태그로 사물함을 여는 유스케이스.
     * <p>
     * 캐비넷을 여는 것은 트리거(MQTT/REST)와 무관한 도메인 행위라 여기서 발행한다.
     * 반면 transactionId 응답이나 실패 통보는 MQTT 프로토콜에만 필요하므로 핸들러가 담당한다.
     * <p>
     * 나중에 대여 이력 기록 등 상태 변경이 붙으면 DB 작업만 별도 @Transactional 메서드로 분리하고
     * 발행은 커밋 이후에 해야 한다. 트랜잭션 안에서 발행하면 롤백돼도 사물함은 이미 물리적으로 열린다.
     *
     * @throws BusinessException 미등록 카드이거나 열어야 할 사물함이 없는 경우
     */
    public void openCabinetByCard(String controllerId, String cardUid, String transactionId) {
        //해당 카드키와 매핑된 방이 없다
        String roomNumber = rentMapper.findRoomNumber(controllerId, cardUid);
        if (roomNumber == null) {
            throw new BusinessException(ErrorCode.RFID_NOT_REGISTERED);
        }

        //rent 테이블에 해당 방에서 사용 중인 보드게임이나 대여를 원하는 보드게임이 없다(status = RENT or USING)
        //사본에 사물함이 지정돼 있지 않은 경우도 열 곳이 없는 것과 같다
        CabinetOpenTarget target = rentMapper.findCabinetOpenTarget(roomNumber);
        if (target == null || target.getCabinetNumber() == null) {
            mqttPublisher.transactionComplete(controllerId, transactionId);
            log.info("openCabinetByCard 트랜잭션 완료 - controllerId={}, transactionId={}",
                    controllerId, transactionId);
            return;
        }

        // 컨트롤러가 상태 보고에 그대로 돌려주는 값들이다.
        // step 은 cabinet_history 적재 규칙과 같은 식으로 계산해 이 명령과 뒤따르는 OPEN 이력을 맞춘다.
        int step = cabinetMapper.resolveNextStep(transactionId);
        String mode = toOpenMode(target.getRentStatus());
        int cabinetNumber = target.getCabinetNumber();

        mqttPublisher.openCabinet(controllerId, cabinetNumber, transactionId, step, mode);
        log.info("사물함 열기 명령 - controllerId={}, room={}, cabinetNumber={}, step={}, mode={}",
                controllerId, roomNumber, cabinetNumber, step, mode);
    }

    /**
     * 사물함을 여는 이유. 픽업 대기(RENT)면 수령, 사용 중(USING)이면 반납이다.
     * <p>
     * CabinetService 가 닫힘 보고를 픽업/반납으로 가르는 기준과 같은 규칙이라,
     * 여기서 알려 준 mode 와 실제로 확정되는 전이가 일치한다.
     */
    public String toOpenMode(String rentStatus) {
        if (StatusUtil.STATUS_RENT_USING.equals(rentStatus)) {
            return StatusUtil.CABINET_OPEN_MODE_RETURN;
        }
        if (StatusUtil.STATUS_RENT_RENT.equals(rentStatus)) {
            return StatusUtil.CABINET_OPEN_MODE_RECEIVE;
        }
        // 조회가 RENT/USING 만 고르므로 여기 도달하면 조회 조건과 이 분기가 어긋났다는 뜻이다
        throw new BusinessException(ErrorCode.INVALID_INPUT);
    }
}
