package com.ssafy.boardgame.mqtt.handler;

import com.ssafy.boardgame.mqtt.MqttTopicHandler;
import com.ssafy.boardgame.mqtt.MqttTopicMatcher;
import com.ssafy.boardgame.mqtt.MqttSubTopics;
import com.ssafy.boardgame.mqtt.dto.McViolationEvent;
import com.ssafy.boardgame.service.McService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * /room/{roomNumber}/mc/event/violation 수신 핸들러.
 * 진행자가 잡아낸 규칙 위반을 받아 적재한다.
 * <p>
 * 손님에게 알리는 것은 태블릿이 같은 토픽을 브로커에서 직접 구독해서 한다 -
 * 여기서 중계하지 않는다. 서버는 집계용 기록만 담당한다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class McViolationHandler implements MqttTopicHandler {

    private final ObjectMapper objectMapper;
    private final McService mcService;

    @Override
    public String topicFilter() {
        return MqttSubTopics.MC_VIOLATION;
    }

    @Override
    public void handle(String topic, String payload) {
        String roomNumber = MqttTopicMatcher.wildcardValues(topicFilter(), topic).get(0);

        log.info("진행자 규칙 위반 알림 수신 - roomNumber={}, payload={}", roomNumber, payload);

        McViolationEvent event;
        try {
            event = objectMapper.readValue(payload, McViolationEvent.class);
        } catch (Exception e) {
            // 태블릿은 같은 메시지를 따로 받으므로 여기서 멈춰도 손님 화면에는 영향이 없다.
            log.warn("violation 페이로드를 해석할 수 없다 - topic={}, payload={}", topic, payload, e);
            return;
        }

        mcService.recordViolation(roomNumber, event);
    }
}
