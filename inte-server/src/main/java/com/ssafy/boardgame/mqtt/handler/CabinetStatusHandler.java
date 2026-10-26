package com.ssafy.boardgame.mqtt.handler;

import com.ssafy.boardgame.mqtt.MqttSubTopics;
import com.ssafy.boardgame.mqtt.MqttTopicHandler;
import com.ssafy.boardgame.mqtt.MqttTopicMatcher;
import com.ssafy.boardgame.mqtt.dto.CabinetStatus;
import com.ssafy.boardgame.service.CabinetService;
import com.ssafy.boardgame.util.StatusUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

import java.util.List;

/**
 * /cabinet/{controllerId}/{cabinetNumber}/status 수신 핸들러.
 * <p>
 * REST 의 컨트롤러와 같은 위치다. 토픽/페이로드를 도메인 인자로 바꿔 서비스에 넘기는 것까지만 담당한다.
 * 이 토픽은 컨트롤러로 되돌려줄 결과 토픽이 없으므로 BusinessException 을 잡지 않는다.
 * (미등록 사물함 등은 설정 오류이므로 MqttMessageDispatcher 가 남기는 에러 로그로 드러나는 편이 낫다)
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class CabinetStatusHandler implements MqttTopicHandler {

    private final ObjectMapper objectMapper;
    private final CabinetService cabinetService;

    @Override
    public String topicFilter() {
        return MqttSubTopics.CABINET_STATUS;
    }

    @Override
    public void handle(String topic, String payload) {
        List<String> wildcards = MqttTopicMatcher.wildcardValues(topicFilter(), topic);
        String controllerId = wildcards.get(0);
        String cabinetNumber = wildcards.get(1);

        log.info("캐비넷 상태 수신 - controllerId={}, cabinetNumber={}, payload={}", controllerId, cabinetNumber, payload);

        // 토픽 세그먼트도 외부 입력이다. 숫자가 아니면 어느 사물함인지 특정할 수 없다
        long cabinetId;
        try {
            cabinetId = Long.parseLong(cabinetNumber);
        } catch (NumberFormatException e) {
            log.warn("사물함 번호가 숫자가 아님 - topic={}", topic);
            return;
        }

        CabinetStatus cabinetStatus = objectMapper.readValue(payload, CabinetStatus.class);

        // 외부에서 오는 페이로드는 스키마를 신뢰할 수 없다
        String status = cabinetStatus.getStatus();
        if (!StatusUtil.STATUS_CABINET_OPEN.equals(status) && !StatusUtil.STATUS_CABINET_CLOSED.equals(status)) {
            log.warn("알 수 없는 사물함 상태 - topic={}, status={}, payload={}", topic, status, payload);
            return;
        }

        // controllerId 는 카드가 어느 방 것인지 찾을 때, transactionId 는 어느 대여의 개폐인지
        // 특정할 때 필요하다. 둘 다 없으면 서비스가 이력만 남긴다.
        cabinetService.recordStatus(controllerId, cabinetId, status, cabinetStatus.getTransactionId(), cabinetStatus.getMode());
    }
}
