package com.ssafy.boardgame.mqtt.handler;

import com.ssafy.boardgame.mqtt.MqttTopicHandler;
import com.ssafy.boardgame.mqtt.MqttSubTopics;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

/**
 * MqttTestController 로 발행한 메시지를 확인하기 위한 핸들러.
 * 구독 토픽은 등록된 핸들러 목록으로 결정되므로, 이 핸들러가 없으면 test/topic 은 수신되지 않는다.
 */
@Slf4j
@Component
public class TestTopicHandler implements MqttTopicHandler {

    @Override
    public String topicFilter() {
        return MqttSubTopics.TEST;
    }

    @Override
    public void handle(String topic, String payload) {
        log.info("MQTT 테스트 수신 - topic={}, payload={}", topic, payload);
    }
}
