package com.ssafy.boardgame.mqtt;

/**
 * 서버 -> 컨트롤러 발행 토픽.
 * <p>
 * 상수가 아니라 메서드로만 두는 이유: 상수로 두면 핸들러의 {@code topicFilter()} 가 반환할 수 있고,
 * 그 순간 서버가 자기 발행을 구독해서 무한 에코 루프가 된다. 메서드는 인자를 요구하므로 컴파일 단계에서 막힌다.
 * 또한 여기서 만드는 토픽은 {@link MqttSubTopics} 의 어떤 필터에도 매칭되지 않아야 한다.
 */
public class MqttPubTopics {

    /** 캐비넷 열기 : /cabinet/{controllerId}/{cabinetNumber}/open */
    public static String cabinetOpen(String controllerId, int cabinetNumber) {
        return "/cabinet/%s/%d/open".formatted(controllerId, cabinetNumber);
    }

    /**
     * RFID 태그 처리 결과 : /cabinet/{controllerId}/card/result
     * <p>
     * 4레벨이라 3레벨 필터인 {@link MqttSubTopics#RFID_CARD} 에 매칭되지 않는다.
     * 이 토픽에는 절대 핸들러를 만들지 말 것(구독이 붙어 루프가 생긴다).
     */
    public static String cardResult(String controllerId) {
        return "/cabinet/%s/card/result".formatted(controllerId);
    }

    /** 트랜잭션 완료(더 이상 열 캐비넷이 없다)
     * /cabinet/{controllerId}/complete
     */
    public static String transactionComplete(String controllerId) {
        return "/cabinet/%s/complete".formatted(controllerId);
    }

    /** wake word 수신 시작 지시 : /room/{roomNumber}/wake/start-listen */
    public static String wakeStartListen(String roomNumber) {
        return "/room/%s/wake/start-listen".formatted(roomNumber);
    }

    /** wake word 수신 중지 지시 : /room/{roomNumber}/wake/stop-listen */
    public static String wakeStopListen(String roomNumber) {
        return "/room/%s/wake/stop-listen".formatted(roomNumber);
    }

    /** QnA 시작 지시 : /room/{roomNumber}/qna/start */
    public static String qnaStart(String roomNumber) {
        return "/room/%s/qna/start".formatted(roomNumber);
    }

    /**
     * 예약한 게임이 반납됐다는 알림 : /room/{roomNumber}/reservation/ready
     * <p>
     * 3번째 세그먼트가 reservation 이라 같은 레벨 수의 {@link MqttSubTopics#WAKE_STATUS},
     * {@link MqttSubTopics#QNA_READY} 어느 쪽에도 매칭되지 않는다.
     */
    public static String reservationReady(String roomNumber) {
        return "/room/%s/reservation/ready".formatted(roomNumber);
    }

    /** 진행자 시작 지시 : /room/{roomNumber}/mc/cmd/start */
    public static String mcStart(String roomNumber) {
        return "/room/%s/mc/cmd/start".formatted(roomNumber);
    }

    /** 진행자 분석 지시 : /room/{roomNumber}/mc/cmd/analyze */
    public static String mcAnalyze(String roomNumber) {
        return "/room/%s/mc/cmd/analyze".formatted(roomNumber);
    }

    /** 진행자 정상 종료 지시 : /room/{roomNumber}/mc/cmd/finish */
    public static String mcFinish(String roomNumber) {
        return "/room/%s/mc/cmd/finish".formatted(roomNumber);
    }

    /**
     * 보드게임 재고 변경 방송 : /boardgame/event
     * <p>
     * 방/컨트롤러로 스코프하지 않는 유일한 발행 토픽이다 - 대여·반납은 모든 방의 재고
     * 표시에 영향을 주므로 한 방에만 보내면 나머지 방은 변화를 영영 모른다.
     * {@link MqttSubTopics} 의 필터는 전부 /room/... 또는 /cabinet/... 로 시작해서
     * 이 토픽에는 매칭되지 않는다.
     */
    public static String boardGameEvent() {
        return "/boardgame/event";
    }
}
