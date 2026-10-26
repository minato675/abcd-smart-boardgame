package com.ssafy.boardgame.mqtt.handler;

import com.ssafy.boardgame.mqtt.MqttTopicHandler;
import com.ssafy.boardgame.mqtt.MqttTopicMatcher;
import com.ssafy.boardgame.mqtt.MqttSubTopics;
import com.ssafy.boardgame.service.QnaService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

/**
 * /room/{roomNumber}/qna/ready 수신 핸들러.
 * QnA 서버가 준비되면 알림을 받는다.
 * <p>
 * 준비 여부는 토픽 자체가 신호라 페이로드를 파싱하지 않는다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class QnaReadyHandler implements MqttTopicHandler {

    private final QnaService qnaService;

    @Override
    public String topicFilter() {
        return MqttSubTopics.QNA_READY;
    }

    @Override
    public void handle(String topic, String payload) {
        String roomNumber = MqttTopicMatcher.wildcardValues(topicFilter(), topic).get(0);

        log.info("QnA 준비 완료 수신 - roomNumber={}, payload={}", roomNumber, payload);

        qnaService.ready(roomNumber);
    }
}
