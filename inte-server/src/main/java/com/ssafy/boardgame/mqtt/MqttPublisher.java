package com.ssafy.boardgame.mqtt;

import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.mqtt.dto.BoardGameEvent;
import com.ssafy.boardgame.mqtt.dto.BoardGameEventType;
import com.ssafy.boardgame.mqtt.dto.CabinetOpen;
import com.ssafy.boardgame.mqtt.dto.McAnalyze;
import com.ssafy.boardgame.mqtt.dto.McCommand;
import com.ssafy.boardgame.mqtt.dto.McStart;
import com.ssafy.boardgame.mqtt.dto.MqttError;
import com.ssafy.boardgame.mqtt.dto.QnaStart;
import com.ssafy.boardgame.mqtt.dto.ReservationReady;
import com.ssafy.boardgame.mqtt.dto.TransactionComplete;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * 서버 -> 컨트롤러 발행 창구.
 * 직렬화와 토픽 결정을 여기 모아두고, 핸들러/서비스는 "무엇을 알린다"만 신경 쓴다.
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class MqttPublisher {

    /** 실을 값이 없는 명령의 페이로드. 빈 문자열은 파싱이 깨지므로 빈 JSON 을 보낸다. */
    private static final String EMPTY_PAYLOAD = "{}";

    private final MqttGateway mqttGateway;
    private final ObjectMapper objectMapper;

    /** 캐비넷 열기 명령 */
    public void openCabinet(String controllerId, int cabinetNumber, String transactionId, int step, String mode) {
        String payload = objectMapper.writeValueAsString(new CabinetOpen(transactionId, step, mode));
        log.info("openCabinet payload : {}", payload);
        mqttGateway.sendToMqtt(MqttPubTopics.cabinetOpen(controllerId, cabinetNumber),
                payload);
    }

    /** 트랜잭션 완료 명령 */
    public void transactionComplete(String controllerId, String transactionId) {
        String payload = objectMapper.writeValueAsString(new TransactionComplete(transactionId));
        log.info("transactionComplete payload : {}", payload);
        mqttGateway.sendToMqtt(MqttPubTopics.transactionComplete(controllerId),
                payload);
    }

    /**
     * 카드 태그 처리 실패 통보.
     * 수신 토픽이 아니라 별도 결과 토픽으로 보낸다(수신 토픽으로 보내면 자기 메시지를 다시 받아 무한 루프).
     */
    public void cardError(String controllerId, String transactionId, ErrorCode errorCode) {
        String payload = objectMapper.writeValueAsString(
                new MqttError(transactionId, errorCode.name(), errorCode.getMessage()));
        log.info("cardError payload : {}", payload);
        mqttGateway.sendToMqtt(MqttPubTopics.cardResult(controllerId), payload);
    }

    /** 룰 설명(QnA) 시작 명령 */
    public void qnaStart(String roomNumber, String transactionId, String boardGameName) {
        String payload = objectMapper.writeValueAsString(
                new QnaStart(transactionId, boardGameName));
        log.info("qnaStart payload : {}", payload);
        mqttGateway.sendToMqtt(MqttPubTopics.qnaStart(roomNumber), payload);
    }

    /** wake word 수신 중지 명령. 실을 값이 없어 빈 JSON 을 보낸다. */
    public void wakeStopListen(String roomNumber) {
        log.info("wakeStopListen - roomNumber={}", roomNumber);
        mqttGateway.sendToMqtt(MqttPubTopics.wakeStopListen(roomNumber), EMPTY_PAYLOAD);
    }

    /** wake word 수신 재개 명령. 실을 값이 없어 빈 JSON 을 보낸다. */
    public void wakeStartListen(String roomNumber) {
        log.info("wakeStartListen - roomNumber={}", roomNumber);
        mqttGateway.sendToMqtt(MqttPubTopics.wakeStartListen(roomNumber), EMPTY_PAYLOAD);
    }

    /** 예약한 게임 반납 알림 (태블릿 팝업) */
    public void reservationReady(String roomNumber, Long reservationId, Long boardGameId,
                                 String boardGameName, int timeoutSec) {
        String payload = objectMapper.writeValueAsString(
                new ReservationReady(reservationId, boardGameId, boardGameName, timeoutSec));
        log.info("reservationReady payload : {}", payload);
        mqttGateway.sendToMqtt(MqttPubTopics.reservationReady(roomNumber), payload);
    }

    /** AI 심판 시작 명령. playerCount 로 진행자가 좌석별 상태를 준비한다. */
    public void mcStart(String roomNumber, String sessionId, String boardGameName, int playerCount) {
        String payload = objectMapper.writeValueAsString(
                new McStart(sessionId, boardGameName, playerCount));
        log.info("mcStart payload : {}", payload);
        mqttGateway.sendToMqtt(MqttPubTopics.mcStart(roomNumber), payload);
    }

    /** AI 심판 분석 지시 (턴 넘기기). seat 은 방금 차례를 마친 좌석이다. */
    public void mcAnalyze(String roomNumber, String sessionId, int seat) {
        String payload = objectMapper.writeValueAsString(new McAnalyze(sessionId, seat));
        log.info("mcAnalyze payload : {}", payload);
        mqttGateway.sendToMqtt(MqttPubTopics.mcAnalyze(roomNumber), payload);
    }

    /** AI 심판 정상 종료 지시 */
    public void mcFinish(String roomNumber, String sessionId) {
        String payload = objectMapper.writeValueAsString(new McCommand(sessionId));
        log.info("mcFinish payload : {}", payload);
        mqttGateway.sendToMqtt(MqttPubTopics.mcFinish(roomNumber), payload);
    }

    /**
     * 보드게임 재고 변경 방송. 대여/반납이 일어난 방과 무관하게 모든 태블릿에 나간다 -
     * 다른 방의 목록 화면도 같은 게임의 재고를 보고 있어 갱신이 필요하다.
     */
    public void boardGameEvent(BoardGameEventType type, Long boardGameId, String roomNumber) {
        String payload = objectMapper.writeValueAsString(
                new BoardGameEvent(type, boardGameId, roomNumber));
        log.info("boardGameEvent payload : {}", payload);
        mqttGateway.sendToMqtt(MqttPubTopics.boardGameEvent(), payload);
    }
}
