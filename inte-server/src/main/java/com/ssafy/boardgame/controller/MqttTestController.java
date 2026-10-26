package com.ssafy.boardgame.controller;

import com.ssafy.boardgame.mqtt.MqttGateway;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

@Slf4j
@RestController
@RequestMapping("/api/mqtt")
@RequiredArgsConstructor
@Tag(name = "테스트 - MQTT", description = "브로커 발행 확인용 개발 편의 API")
public class MqttTestController {

    private final MqttGateway mqttGateway;

    // 기본 토픽으로 발행
    @Operation(summary = "기본 토픽으로 발행",
            description = "`mqtt.default-topic` 설정값으로 메시지를 발행한다. 본문은 평문 문자열이다.")
    @PostMapping("/publish")
    public String publish(@RequestBody String message) {
        mqttGateway.sendToMqtt(message);
        log.info("MQTT 발행: {}", message);
        return "메시지 발행 완료: " + message;
    }

    // 특정 토픽으로 발행
    @Operation(summary = "특정 토픽으로 발행",
            description = "지정한 토픽으로 메시지를 발행한다. 본문은 평문 문자열이다.")
    @PostMapping("/publish/{topic}")
    public String publishToTopic(
            @Parameter(description = "발행할 MQTT 토픽", example = "test/topic", required = true)
            @PathVariable String topic,
            @RequestBody String message) {
        mqttGateway.sendToMqtt(topic, message);
        log.info("MQTT 발행 - Topic: {}, Message: {}", topic, message);
        return "토픽 [" + topic + "] 발행 완료: " + message;
    }
}
