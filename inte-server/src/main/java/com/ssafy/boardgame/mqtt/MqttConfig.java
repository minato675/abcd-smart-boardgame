package com.ssafy.boardgame.mqtt;

import lombok.Getter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;

@Getter
@Configuration
public class MqttConfig {

    @Value("${mqtt.host}")
    private String host;

    @Value("${mqtt.port}")
    private int port;

    @Value("${mqtt.client-id}")
    private String clientId;

    @Value("${mqtt.username:}")
    private String username;

    @Value("${mqtt.password:}")
    private String password;

    @Value("${mqtt.default-topic}")
    private String defaultTopic;

    @Value("${mqtt.qos}")
    private int qos;

    @Bean
    public MqttPahoClientFactory mqttClientFactory() {
        DefaultMqttPahoClientFactory factory = new DefaultMqttPahoClientFactory();
        MqttConnectOptions options = new MqttConnectOptions();
        String brokerUrl = String.format("tcp://%s:%d", host, port);
        options.setServerURIs(new String[]{brokerUrl});

        // 인증이 필요한 경우만 설정
        if (username != null && !username.isEmpty()) {
            options.setUserName(username);
            options.setPassword(password.toCharArray());
        }

        options.setCleanSession(true);
        options.setAutomaticReconnect(true);
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(60);

        factory.setConnectionOptions(options);
        return factory;
    }
}
