package com.ssafy.boardgame.mqtt.handler;

import com.ssafy.boardgame.mqtt.MqttTopicHandler;
import com.ssafy.boardgame.mqtt.MqttTopicMatcher;
import com.ssafy.boardgame.mqtt.MqttSubTopics;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

/**
 * /room/{controllerId}/{roomNumber}/camera/status 수신 핸들러.
 */
@Slf4j
@Component
public class CameraStatusHandler implements MqttTopicHandler {

    @Override
    public String topicFilter() {
        return MqttSubTopics.CAMERA_STATUS;
    }

    @Override
    public void handle(String topic, String payload) {
        String controllerId = MqttTopicMatcher.wildcardValues(topicFilter(), topic).get(0);
        String roomNumber = MqttTopicMatcher.wildcardValues(topicFilter(), topic).get(1);
        log.info("카메라 상태 수신 - controllerId={}, roomNumber={}, payload={}", controllerId, roomNumber, payload);

        // TODO 비즈니스 로직: payload 파싱 후 서비스 호출
    }
}
