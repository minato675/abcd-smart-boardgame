package com.ssafy.boardgame.mqtt;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.Comparator;
import java.util.List;

/**
 * 수신 메시지를 토픽에 맞는 {@link MqttTopicHandler} 로 넘기는 분기 지점.
 * <p>
 * 스프링이 주입해주는 핸들러 목록을 구체적인 필터 순으로 정렬해두고, 먼저 매칭되는 하나에게만 위임한다.
 */
@Slf4j
@Component
public class MqttMessageDispatcher {

    private final List<MqttTopicHandler> handlers;

    public MqttMessageDispatcher(List<MqttTopicHandler> handlers) {
        // cabinet/# 가 cabinet/3/status 를 가로채지 않도록 구체적인 필터를 앞에 둔다
        this.handlers = handlers.stream()
                .sorted(Comparator.comparingInt(
                        (MqttTopicHandler handler) -> MqttTopicMatcher.specificity(handler.topicFilter())).reversed())
                .toList();

        this.handlers.forEach(handler -> log.info("MQTT 핸들러 등록 - filter={}, handler={}",
                handler.topicFilter(), handler.getClass().getSimpleName()));
    }

    /**
     * 구독해야 할 토픽 필터 목록. {@link MqttSubscriberConfig} 가 어댑터를 만들 때 사용한다.
     */
    public List<String> topicFilters() {
        return handlers.stream()
                .map(MqttTopicHandler::topicFilter)
                .distinct()
                .toList();
    }

    public void dispatch(String topic, String payload) {
        if (topic == null) {
            log.warn("MQTT 토픽 헤더 없음 - payload={}", payload);
            return;
        }

        for (MqttTopicHandler handler : handlers) {
            if (!MqttTopicMatcher.matches(handler.topicFilter(), topic)) {
                continue;
            }
            try {
                handler.handle(topic, payload);
            } catch (Exception e) {
                // 여기는 Paho 수신 콜백 스레드다. 예외를 그대로 올리면 이후 수신까지 영향을 받으므로
                // 핸들러 하나의 실패를 로그로 격리한다.
                log.error("MQTT 처리 실패 - topic={}, handler={}, payload={}",
                        topic, handler.getClass().getSimpleName(), payload, e);
            }
            return;
        }

        // 구독은 했는데 처리할 핸들러가 없는 경우 (예: 핸들러 삭제 후 필터만 남음)
        log.warn("MQTT 핸들러 없음 - topic={}, payload={}", topic, payload);
    }
}
