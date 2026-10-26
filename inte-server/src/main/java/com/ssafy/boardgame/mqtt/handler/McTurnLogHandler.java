package com.ssafy.boardgame.mqtt.handler;

import com.ssafy.boardgame.mqtt.MqttTopicHandler;
import com.ssafy.boardgame.mqtt.MqttTopicMatcher;
import com.ssafy.boardgame.mqtt.MqttSubTopics;
import com.ssafy.boardgame.mqtt.dto.McTurnLogEvent;
import com.ssafy.boardgame.service.McService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * /room/{roomNumber}/mc/event/turn-log 수신 핸들러.
 * 진행자가 파악한 마지막 테이블 상태를 받아 적재한다.
 * <p>
 * 태블릿도 같은 토픽을 브로커에서 직접 구독한다 - 여기서 중계하는 것이 아니라
 * 서버는 기록을, 화면은 표시를 각자 한다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class McTurnLogHandler implements MqttTopicHandler {

    private final ObjectMapper objectMapper;
    private final McService mcService;

    @Override
    public String topicFilter() {
        return MqttSubTopics.MC_TURN_LOG;
    }

    @Override
    public void handle(String topic, String payload) {
        String roomNumber = MqttTopicMatcher.wildcardValues(topicFilter(), topic).get(0);

        log.info("진행자 턴 로그 수신 - roomNumber={}, payload={}", roomNumber, payload);

        McTurnLogEvent event;
        try {
            event = objectMapper.readValue(payload, McTurnLogEvent.class);
        } catch (Exception e) {
            // 되돌려줄 결과 토픽도, 되살릴 장치 상태도 없다. 기록을 포기하고 로그만 남긴다.
            log.warn("turn-log 페이로드를 해석할 수 없다 - topic={}, payload={}", topic, payload, e);
            return;
        }

        mcService.recordTurnLog(roomNumber, event);
    }
}
