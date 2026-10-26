package com.ssafy.boardgame.mqtt.handler;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.mapper.RoomMapper;
import com.ssafy.boardgame.mqtt.MqttPublisher;
import com.ssafy.boardgame.mqtt.MqttSubTopics;
import com.ssafy.boardgame.mqtt.MqttTopicHandler;
import com.ssafy.boardgame.mqtt.MqttTopicMatcher;
import com.ssafy.boardgame.mqtt.dto.RfidCard;
import com.ssafy.boardgame.service.CabinetService;
import com.ssafy.boardgame.service.RentService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * /cabinet/+/card 수신 핸들러.
 * <p>
 * REST 의 컨트롤러와 같은 위치다. 토픽/페이로드를 도메인 인자로 바꿔 서비스에 넘기고,
 * 실패를 MQTT 프로토콜 응답으로 변환하는 것까지만 담당한다. 도메인 조회와 분기는 서비스에 있다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class RfidCardHandler implements MqttTopicHandler {

    private final ObjectMapper objectMapper;
    private final RentService rentService;
    private final CabinetService cabinetService;
    private final MqttPublisher mqttPublisher;
    private final RoomMapper roomMapper;

    @Override
    public String topicFilter() {
        return MqttSubTopics.RFID_CARD;
    }

    @Override
    public void handle(String topic, String payload) {
        String controllerId = MqttTopicMatcher.wildcardValues(topicFilter(), topic).get(0);
        log.info("rfid 수신 - controllerId={}, payload={}", controllerId, payload);

        RfidCard card = objectMapper.readValue(payload, RfidCard.class);

        // 외부에서 오는 페이로드는 스키마를 신뢰할 수 없다
        if (card.getCardUid() == null || card.getCardUid().isBlank()) {
            log.warn("cardUid 없는 페이로드 - topic={}, payload={}", topic, payload);
            return;
        }
        // cabinet_transaction.transaction_id 가 NOT NULL 이고, 없으면 컨트롤러에 결과를 돌려줄 수도
        // 개폐 보고를 이 태그와 이을 수도 없다. 프로토콜상 필수값이라 여기서 막는다.
        if (card.getTransactionId() == null || card.getTransactionId().isBlank()) {
            log.warn("transactionId 없는 페이로드 - topic={}, payload={}", topic, payload);
            return;
        }

        String roomNumber = roomMapper.findRoomByRfid(card.getCardUid());

        if(roomNumber == null) {
            log.warn("룸과 매핑되지 않은 cardUid - topic={}, payload={}", topic, payload);
            return;
        }

        // 태그 시점에 거래를 먼저 남긴다. 아래 열기 시도가 실패해도 롤백되지 않아야 하므로
        // 서비스의 별도 트랜잭션으로 커밋시킨 뒤 진행한다.
        cabinetService.recordCardTransaction(card.getTransactionId(), card.getCardUid(), roomNumber);

        try {
            rentService.openCabinetByCard(controllerId, card.getCardUid(), card.getTransactionId());
        } catch (BusinessException e) {
            // 예상된 실패. MQTT 에는 GlobalExceptionHandler(@RestControllerAdvice) 가 걸리지 않으므로
            // 여기서 프로토콜 응답으로 변환한다. 예상 못 한 예외는 MqttMessageDispatcher 가 격리 로깅한다.
            log.warn("카드 태그 거부 - code={}, controllerId={}, cardUid={}",
                    e.getErrorCode(), controllerId, card.getCardUid());
            mqttPublisher.cardError(controllerId, card.getTransactionId(), e.getErrorCode());
        }
    }
}
