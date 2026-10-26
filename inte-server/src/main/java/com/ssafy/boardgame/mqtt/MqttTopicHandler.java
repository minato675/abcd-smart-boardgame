package com.ssafy.boardgame.mqtt;

/**
 * 토픽 하나(또는 와일드카드 필터 하나)를 담당하는 수신 핸들러.
 * <p>
 * 구현체를 {@code @Component} 로 등록하면 {@link MqttMessageDispatcher} 가 자동으로 수집하고,
 * {@link MqttSubscriberConfig} 가 그 목록을 그대로 구독한다.
 * 즉 핸들러만 추가하면 구독까지 같이 붙으므로, 토픽 목록을 별도로 관리할 필요가 없다.
 */
public interface MqttTopicHandler {

    /**
     * 담당할 토픽 필터. 와일드카드('+', '#') 사용 가능.
     * {@link MqttSubTopics} 상수를 반환하는 것을 권장한다.
     */
    String topicFilter();

    /**
     * @param topic   실제 수신 토픽 (필터가 아닌 구체 토픽)
     * @param payload 문자열 페이로드 (DefaultPahoMessageConverter 기본 변환 결과)
     */
    void handle(String topic, String payload);
}
