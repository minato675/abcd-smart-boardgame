package com.ssafy.boardgame.mqtt.handler;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.mqtt.MqttPublisher;
import com.ssafy.boardgame.mqtt.MqttSubTopics;
import com.ssafy.boardgame.mqtt.MqttTopicHandler;
import com.ssafy.boardgame.mqtt.MqttTopicMatcher;
import com.ssafy.boardgame.mqtt.dto.WakeStatus;
import com.ssafy.boardgame.service.McService;
import com.ssafy.boardgame.service.QnaService;
import com.ssafy.boardgame.util.StatusUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * /room/{roomNumber}/wake/status 수신 핸들러.
 * wake word 상태(call / finish)를 받는다.
 * <p>
 * REST 의 컨트롤러와 같은 위치다. 토픽/페이로드를 도메인 인자로 바꿔 서비스에 넘기는 것까지만 담당한다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class WakeStatusHandler implements MqttTopicHandler {

    private final ObjectMapper objectMapper;
    private final QnaService qnaService;
    private final McService mcService;
    private final MqttPublisher mqttPublisher;
    @Override
    public String topicFilter() {
        return MqttSubTopics.WAKE_STATUS;
    }

    @Override
    public void handle(String topic, String payload) {
        String roomNumber = MqttTopicMatcher.wildcardValues(topicFilter(), topic).get(0);

        log.info("wake word 상태 수신 - roomNumber={}, payload={}", roomNumber, payload);

        WakeStatus wakeStatus = objectMapper.readValue(payload, WakeStatus.class);

        // 외부에서 오는 페이로드는 스키마를 신뢰할 수 없다.
        // 아는 상태만 골라서 처리한다 - '아니면 finish' 로 두면 오타나 새 상태값이
        // 턴 넘기기로 잘못 이어진다.
        String status = wakeStatus.getStatus();

        if (StatusUtil.STATUS_WAKE_CALL.equals(status)) {
            //QnaService.start에서 wakeStopListen 호출해서 여기서는 제거
            startQna(roomNumber);
        } else if (StatusUtil.STATUS_WAKE_FINISH.equals(status)) {
            mqttPublisher.wakeStopListen(roomNumber);
            passTurn(roomNumber);
        } else {
            log.warn("알 수 없는 wake word 상태 - topic={}, status={}, payload={}", topic, status, payload);
        }
    }

    /** 호출어 -> 룰 설명 시작. 태블릿의 '규칙 물어보기' 버튼과 같은 동작이다. */
    private void startQna(String roomNumber) {
        try {
            qnaService.start(roomNumber);
        } catch (BusinessException e) {
            // 예상된 실패(대여 중인 게임이 없는 방에서 호출한 경우 등).
            // MQTT 에는 GlobalExceptionHandler(@RestControllerAdvice) 가 걸리지 않고 이 토픽에는
            // 되돌려줄 결과 토픽도 없으므로 여기서 로그로 끝낸다.
            // 예상 못 한 예외는 MqttMessageDispatcher 가 격리 로깅한다.
            log.warn("wake word 호출로 QnA 시작 실패 - code={}, roomNumber={}", e.getErrorCode(), roomNumber);
            mqttPublisher.wakeStartListen(roomNumber);
        }
    }

    /**
     * 발화 종료 -> 턴 넘기기. 태블릿 패널의 '턴 넘기기' 버튼과 같은 동작이다.
     * <p>
     * 심판이 꺼져 있는 방에서도 이 신호는 올라온다(호출어 장치는 심판 상태를 모른다).
     * 그때는 MC_SESSION_NOT_FOUND 가 나는 것이 정상이라 로그만 남긴다.
     */
    private void passTurn(String roomNumber) {
        try {
            mcService.analyze(roomNumber);
        } catch (BusinessException e) {
            log.warn("wake word 종료로 턴 넘기기 실패 - code={}, roomNumber={}", e.getErrorCode(), roomNumber);
            mqttPublisher.wakeStartListen(roomNumber);
        }
    }
}
