package com.ssafy.boardgame.mqtt.handler;

import com.ssafy.boardgame.mqtt.MqttTopicHandler;
import com.ssafy.boardgame.mqtt.MqttTopicMatcher;
import com.ssafy.boardgame.mqtt.MqttSubTopics;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

/**
 * room/{roomNumber}/rummikub 수신 핸들러.
 */
@Slf4j
@Component
public class RummiKubLogHandler implements MqttTopicHandler {

    @Override
    public String topicFilter() {
        return MqttSubTopics.RUMMIKUB_LOG;
    }

    @Override
    public void handle(String topic, String payload) {
        // 토픽에 실려온 식별자 추출 (room/3/rummikub -> "3")
        String roomNumber = MqttTopicMatcher.wildcardValues(topicFilter(), topic).get(0);

        log.info("루미큐브 로그 수신 - roomNumber={}, payload={}", roomNumber, payload);

        // TODO 비즈니스 로직: payload 파싱 후 서비스 호출
    }
}