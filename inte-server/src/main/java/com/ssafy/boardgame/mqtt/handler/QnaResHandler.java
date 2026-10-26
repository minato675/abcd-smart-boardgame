package com.ssafy.boardgame.mqtt.handler;

import com.ssafy.boardgame.mqtt.MqttTopicHandler;
import com.ssafy.boardgame.mqtt.MqttTopicMatcher;
import com.ssafy.boardgame.mqtt.MqttSubTopics;
import com.ssafy.boardgame.mqtt.dto.QnaRes;
import com.ssafy.boardgame.service.QnaService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * /room/{roomNumber}/qna/res 수신 핸들러.
 * QnA 서버가 전달한 req / res 를 받아 로그로 남기고 wake word 를 되살린다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class QnaResHandler implements MqttTopicHandler {

    private final ObjectMapper objectMapper;
    private final QnaService qnaService;

    @Override
    public String topicFilter() {
        return MqttSubTopics.QNA_RES;
    }

    @Override
    public void handle(String topic, String payload) {
        String roomNumber = MqttTopicMatcher.wildcardValues(topicFilter(), topic).get(0);

        log.info("QnA 응답 수신 - roomNumber={}, payload={}", roomNumber, payload);

        QnaRes qnaRes;
        try {
            qnaRes = objectMapper.readValue(payload, QnaRes.class);
        } catch (Exception e) {
            // 다른 핸들러와 달리 여기서 멈추지 않는다. 페이로드가 깨졌어도 응답이 왔다는
            // 사실은 확실하므로, 로그를 포기하더라도 wake word 는 되살려야 한다.
            // 여기서 반환하면 그 방은 타임아웃이 돌 때까지 마이크가 꺼진 채로 남는다.
            log.warn("qna/res 페이로드를 해석할 수 없다 - topic={}, payload={}", topic, payload, e);
            qnaRes = new QnaRes();
        }

        qnaService.result(roomNumber, qnaRes);
    }
}
