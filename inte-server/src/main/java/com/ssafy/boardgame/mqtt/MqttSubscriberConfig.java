package com.ssafy.boardgame.mqtt;

import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.core.MessageProducer;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.util.Assert;

import java.util.Arrays;
import java.util.List;
import java.util.UUID;

@Slf4j
@Configuration
public class MqttSubscriberConfig {

    private final MqttConfig mqttConfig;
    private final MqttPahoClientFactory clientFactory;
    private final MqttMessageDispatcher dispatcher;

    public MqttSubscriberConfig(MqttConfig mqttConfig,
                                MqttPahoClientFactory clientFactory,
                                MqttMessageDispatcher dispatcher) {
        this.mqttConfig = mqttConfig;
        this.clientFactory = clientFactory;
        this.dispatcher = dispatcher;
    }

    @Bean
    public MessageChannel mqttInboundChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageProducer inbound() {
        // 구독 토픽은 등록된 MqttTopicHandler 들의 필터로 결정된다.
        // 토픽 목록을 따로 관리하지 않으므로 "핸들러는 만들었는데 구독을 안 붙인" 실수가 생기지 않는다.
        List<String> topicFilters = dispatcher.topicFilters();
        Assert.notEmpty(topicFilters,
                "구독할 MQTT 토픽이 없다. MqttTopicHandler 구현체를 하나 이상 @Component 로 등록해야 한다.");

        String[] topics = topicFilters.toArray(String[]::new);
        MqttPahoMessageDrivenChannelAdapter adapter =
                new MqttPahoMessageDrivenChannelAdapter(
                        mqttConfig.getClientId() + UUID.randomUUID(),
                        clientFactory,
                        topics
                );
        adapter.setCompletionTimeout(5000);
        adapter.setConverter(new DefaultPahoMessageConverter());

        // QoS 배열 길이는 토픽 개수와 맞아야 한다 -> mqtt 내부 규칙
        int[] qosPerTopic = new int[topics.length];
        Arrays.fill(qosPerTopic, mqttConfig.getQos());
        adapter.setQos(qosPerTopic);

        adapter.setOutputChannel(mqttInboundChannel());

        log.info("MQTT 구독 토픽 {}개 - {}", topics.length, topicFilters);
        return adapter;
    }

    @Bean
    @ServiceActivator(inputChannel = "mqttInboundChannel")
    public MessageHandler mqttInboundHandler() {
        return message -> {
            String topic = (String) message.getHeaders().get(MqttHeaders.RECEIVED_TOPIC);
            String payload = String.valueOf(message.getPayload());
            log.debug("MQTT 수신 - topic={}, payload={}", topic, payload);
            dispatcher.dispatch(topic, payload);
        };
    }
}
