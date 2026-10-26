package com.ssafy.boardgame.controller;

import com.ssafy.boardgame.mapper.BoardGameItemMapper;
import com.ssafy.boardgame.mqtt.MqttGateway;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.Map;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 헬스체크 / DB 연결 확인 / MQTT 발행 등 운영·디버그용 엔드포인트.
 * 비즈니스 로직이 없으므로 라우팅과 위임만 고정한다.
 */
@WebMvcTest({HealthController.class, DbTestController.class, MqttTestController.class})
@DisplayName("운영/디버그 엔드포인트")
class SupportControllerTest {

    @Autowired private MockMvc mockMvc;

    @MockitoBean private BoardGameItemMapper boardGameItemMapper;
    @MockitoBean private MqttGateway mqttGateway;

    @Nested
    @DisplayName("GET /health")
    class Health {

        @Test
        @DisplayName("200 과 OK 를 반환한다")
        void health_returnsOk() throws Exception {
            mockMvc.perform(get("/health"))
                    .andExpect(status().isOk())
                    .andExpect(content().string("OK"));
        }
    }

    @Nested
    @DisplayName("GET /db/test")
    class DbTest {

        @Test
        @DisplayName("매퍼가 돌려준 행을 그대로 JSON 배열로 반환한다")
        void dbTest_returnsRows() throws Exception {
            given(boardGameItemMapper.findAll()).willReturn(List.of(
                    Map.of("item_id", 1, "board_game_id", 1, "status", "AVAILABLE"),
                    Map.of("item_id", 2, "board_game_id", 1, "status", "RENTED")));

            mockMvc.perform(get("/db/test"))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.length()").value(2))
                    .andExpect(jsonPath("$[0].status").value("AVAILABLE"));
        }

        @Test
        @DisplayName("행이 없으면 빈 배열이다")
        void dbTest_noRows_returnsEmptyArray() throws Exception {
            given(boardGameItemMapper.findAll()).willReturn(List.of());

            mockMvc.perform(get("/db/test"))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.length()").value(0));
        }
    }

    @Nested
    @DisplayName("POST /api/mqtt/publish")
    class MqttPublish {

        @Test
        @DisplayName("기본 토픽으로 발행하고 200 을 반환한다")
        void publish_sendsToDefaultTopic() throws Exception {
            mockMvc.perform(post("/api/mqtt/publish")
                            .contentType(MediaType.TEXT_PLAIN)
                            .content("hello"))
                    .andExpect(status().isOk())
                    .andExpect(content().string(containsString("hello")));

            then(mqttGateway).should().sendToMqtt("hello");
        }

        @Test
        @DisplayName("토픽을 지정하면 해당 토픽으로 발행한다")
        void publishToTopic_sendsToGivenTopic() throws Exception {
            mockMvc.perform(post("/api/mqtt/publish/cabinet")
                            .contentType(MediaType.TEXT_PLAIN)
                            .content("open"))
                    .andExpect(status().isOk())
                    .andExpect(content().string(containsString("cabinet")))
                    .andExpect(content().string(containsString("open")));

            then(mqttGateway).should().sendToMqtt("cabinet", "open");
        }
    }
}
