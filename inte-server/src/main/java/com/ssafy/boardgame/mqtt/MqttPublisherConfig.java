package com.ssafy.boardgame.mqtt;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

import java.util.UUID;

@Configuration
public class MqttPublisherConfig {

    private final MqttConfig mqttConfig;
    private final MqttPahoClientFactory clientFactory;

    public MqttPublisherConfig(MqttConfig mqttConfig, MqttPahoClientFactory clientFactory) {
        this.mqttConfig = mqttConfig;
        this.clientFactory = clientFactory;
    }

    @Bean
    public MessageChannel mqttOutboundChannel() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "mqttOutboundChannel")
    public MessageHandler mqttOutbound() {
        MqttPahoMessageHandler messageHandler =
                new MqttPahoMessageHandler(mqttConfig.getClientId() + UUID.randomUUID(), clientFactory);
        messageHandler.setAsync(true);
        messageHandler.setDefaultTopic(mqttConfig.getDefaultTopic());
        messageHandler.setDefaultQos(mqttConfig.getQos());
        return messageHandler;
    }
}
