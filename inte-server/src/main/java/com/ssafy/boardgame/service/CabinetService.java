package com.ssafy.boardgame.service;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.dto.ActiveRent;
import com.ssafy.boardgame.dto.CabinetOpenTarget;
import com.ssafy.boardgame.mapper.BoardGameItemMapper;
import com.ssafy.boardgame.mapper.CabinetMapper;
import com.ssafy.boardgame.mapper.RentMapper;
import com.ssafy.boardgame.mqtt.MqttPublisher;
import com.ssafy.boardgame.mqtt.dto.BoardGameEventType;
import com.ssafy.boardgame.util.StatusUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Service
@RequiredArgsConstructor
public class CabinetService {

    private final CabinetMapper cabinetMapper;
    private final RentMapper rentMapper;
    private final BoardGameItemMapper boardGameItemMapper;
    private final MqttPublisher mqttPublisher;
    private final RentService rentService;
    private final ReservationNotifyService reservationNotifyService;
    /**
     * 카드 태그로 시작된 거래를 기록한다.
     * <p>
     * 호출부가 사물함 열기를 시도하기 전에 이것부터 커밋해야 한다. 열기가 거부돼도
     * "누가 언제 태그했는지" 는 남아야 하고, 이후 개폐 보고를 카드와 이을 근거이기도 하다.
     */
    @Transactional
    public void recordCardTransaction(String transactionId, String cardUid, String roomNumber) {
        cabinetMapper.insertCabinetTransaction(transactionId, cardUid, roomNumber);
        log.info("카드 트랜잭션 기록 - transactionId={}, cardUid={}, roomNumber={}", transactionId, cardUid, roomNumber);
    }

    /**
     * 컨트롤러가 올린 사물함 열림/닫힘을 반영한다.
     * <p>
     * 문이 닫힌 것으로 보고되면 그 사물함을 열게 만든 대여를 한 단계 전진시킨다.
     * 상태 · 이력 · 대여 전이를 한 트랜잭션으로 묶는다. 일부만 반영되면 이후 집계를 신뢰할 수 없다.
     *
     * @param controllerId  토픽의 {controllerId}. 카드가 어느 방 것인지 찾을 때 쓴다.
     * @param cabinetId     토픽의 {cabinetNumber}. board_game_item.cabinet_id 와 같은 값이다.
     * @param status        {@link StatusUtil#STATUS_CABINET_OPEN} 또는 {@link StatusUtil#STATUS_CABINET_CLOSED}
     * @param transactionId 카드 태그 때 발급된 거래 키. 없으면 대여를 특정할 수 없어 이력만 남는다.
     * @throws BusinessException 등록되지 않은 사물함 번호인 경우
     */
    @Transactional
    public void recordStatus(String controllerId, long cabinetId, String status, String transactionId, String mode) {
        // 존재 확인과 직전 상태 확인을 한 번에. 행을 잠가서 같은 사물함 메시지가 겹쳐도 순서대로 처리된다.
        String previousStatus = cabinetMapper.findStatusForUpdate(cabinetId);
        if (previousStatus == null) {
            throw new BusinessException(ErrorCode.CABINET_NOT_FOUND);
        }

        cabinetMapper.updateStatus(cabinetId, status);

        String eventType = toEventType(status);
        int step = cabinetMapper.resolveNextStep(transactionId);
        cabinetMapper.insertCabinetHistory(transactionId, cabinetId, eventType, StatusUtil.CABINET_TRIGGERED_BY_USER, step);
        log.info("사물함 이력 적재 - cabinetId={}, status={}, eventType={}", cabinetId, status, eventType);

        // 열린 적 없는데 닫혔다는 보고는 뒤처리 대상이 아니다.
        // QoS 1 은 at-least-once 라서 같은 CLOSED 가 두 번 오는데, 그때 다음 대여를 건드리면 안 된다.
        if (!StatusUtil.STATUS_CABINET_CLOSED.equals(status)) {
            return;
        }
        if (!StatusUtil.STATUS_CABINET_OPEN.equals(previousStatus)) {
            log.info("직전이 열림 상태가 아니라 대여 전이를 건너뛴다 - cabinetId={}, previous={}, transactionId={}",
                    cabinetId, previousStatus, transactionId);
            return;
        }

        advanceRent(controllerId, cabinetId, transactionId);
    }

    /**
     * 닫힘 보고를 대여 한 건의 상태 전이로 옮긴다.
     * transactionId -> 카드 -> 방 -> 진행 중 대여 순으로 좁힌다.
     * 어느 단계든 못 찾으면 이력만 남기고 조용히 끝낸다(개폐 자체는 이미 기록됐다).
     */
    private void advanceRent(String controllerId, long cabinetId, String transactionId) {
        if (transactionId == null || transactionId.isBlank()) {
            log.warn("transactionId 없는 닫힘 보고 - cabinetId={}. 대여를 특정할 수 없다", cabinetId);
            return;
        }

        String cardUid = cabinetMapper.findCardUid(transactionId);
        if (cardUid == null) {
            log.warn("거래에 해당하는 카드 없음 - cabinetId={}, transactionId={}", cabinetId, transactionId);
            return;
        }

        String roomNumber = rentMapper.findRoomNumber(controllerId, cardUid);
        if (roomNumber == null) {
            log.warn("카드에 매핑된 방 없음 - controllerId={}, cardUid={}", controllerId, cardUid);
            return;
        }

        ActiveRent rent = rentMapper.findActiveRent(roomNumber);
        if (rent == null) {
            log.info("방에 진행 중인 대여 없음 - room={}, cabinetId={}", roomNumber, cabinetId);
            return;
        }

        // USING 이 있으면 반납, 없으면(RENT) 픽업. findActiveRent 의 우선순위가 이 분기를 결정한다.
        if (StatusUtil.STATUS_RENT_USING.equals(rent.getStatus())) {
            completeReturn(rent, roomNumber, controllerId, transactionId);
        } else {
            completePickup(rent, roomNumber, controllerId, transactionId);
        }
    }

    /** 픽업 확정. 사본은 계속 RENTED 다(손님이 들고 있다). */
    private void completePickup(ActiveRent rent, String roomNumber, String controllerId, String transactionId) {
        if (rentMapper.markUsing(rent.getRentId()) == 0) {
            log.info("이미 처리된 픽업 - rentId={}", rent.getRentId());
            return;
        }
        log.info("픽업 확정 - room={}, rentId={}, itemId={}",
                roomNumber, rent.getRentId(), rent.getBoardGameItemId());

        mqttPublisher.transactionComplete(controllerId, transactionId);
        log.info("대여 사물함이 닫혔고 트랜잭션 완료 - controllerId={}, transactionId={}",
                controllerId, transactionId);
    }

    /** 반납 확정. 대여를 마감하고 사본을 재고로 되돌린다. */
    private void completeReturn(ActiveRent rent, String roomNumber, String controllerId, String transactionId) {
        if (rentMapper.markReturned(rent.getRentId()) == 0) {
            log.info("이미 처리된 반납 - rentId={}", rent.getRentId());
            return;
        }
        // 반납이 확정된 뒤에만 재고로 되돌린다
        boardGameItemMapper.updateStatus(rent.getBoardGameItemId(), StatusUtil.STATUS_BOARD_AVAILABLE);
        log.info("반납 확정 - room={}, rentId={}, itemId={}",
                roomNumber, rent.getRentId(), rent.getBoardGameItemId());

        // 이 게임의 재고가 늘었다는 걸 모든 방에 알린다 - 남의 방 목록 화면도 이 게임을 보고 있다.
        mqttPublisher.boardGameEvent(BoardGameEventType.RETURN, rent.getBoardGameId(), roomNumber);

        // 이 게임을 기다리던 첫 번째 방에게 팝업을 띄운다.
        // 사본을 되돌린 직후여야 알림 쪽 재고 확인이 방금 돌아온 이 사본을 본다.
        // 아래 '다음 사물함 열기' 보다 먼저 두는 이유는 그쪽에 1초 sleep 이 있어서다.
        reservationNotifyService.notifyFirstWaiting(rent.getBoardGameId());

        //다음 사물함을 열어야 되는지 확인하고 있으면 다음 사물함 오픈 없으면 트랜잭션 완료
        CabinetOpenTarget target = rentMapper.findCabinetOpenTarget(roomNumber);
        if (target == null || target.getCabinetNumber() == null) {
            mqttPublisher.transactionComplete(controllerId, transactionId);
            log.info("반납 사물함이 닫혔고 다음 대여가 없어서 트랜잭션 완료 - controllerId={}, transactionId={}",
                    controllerId, transactionId);
        } else {
            try {
                Thread.sleep(1000);
                // 컨트롤러가 상태 보고에 그대로 돌려주는 값들이다.
                // step 은 cabinet_history 적재 규칙과 같은 식으로 계산해 이 명령과 뒤따르는 OPEN 이력을 맞춘다.
                int step = cabinetMapper.resolveNextStep(transactionId);
                String mode = rentService.toOpenMode(target.getRentStatus());
                int cabinetNumber = target.getCabinetNumber();

                mqttPublisher.openCabinet(controllerId, cabinetNumber, transactionId, step, mode);
                log.info("반납 후 대여 사물함 열기 명령 - controllerId={}, room={}, cabinetNumber={}, step={}, mode={}",
                        controllerId, roomNumber, cabinetNumber, step, mode);
            } catch (Exception e) {
                log.error("반납 후 대여 사물함 오픈 도중 에러 : {}", e.getMessage());
            }

        }
    }

    /** 상태값(CLOSED)과 이력 이벤트명(CLOSE)이 달라서 변환이 필요하다. */
    private String toEventType(String status) {
        if (StatusUtil.STATUS_CABINET_OPEN.equals(status)) {
            return StatusUtil.CABINET_EVENT_OPEN;
        }
        if (StatusUtil.STATUS_CABINET_CLOSED.equals(status)) {
            return StatusUtil.CABINET_EVENT_CLOSE;
        }
        // 핸들러가 걸러낸 뒤에 들어오므로 여기 도달하면 검증이 빠진 호출부가 있다는 뜻이다
        throw new BusinessException(ErrorCode.INVALID_INPUT);
    }
}
