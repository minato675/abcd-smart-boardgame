package com.ssafy.boardgame.mqtt;

/**
 * MQTT 토픽 필터 상수.
 * 구독(핸들러의 topicFilter)과 발행(MqttGateway) 양쪽에서 같은 문자열을 쓰기 위해 한 곳에 모아둔다.
 * '+' 는 한 레벨, '#' 는 이후 전체 레벨에 매칭된다.
 */
public class MqttSubTopics {

    // 발행/수신 테스트용 (mqtt.default-topic 과 동일한 값)
    public static final String TEST = "/default/topic";

    // 컨트롤러 -> 서버 (수신 전용)

    // 캐비넷 상태 : /cabinet/{controllerId}/{cabinetNumber}/status
    public static final String CABINET_STATUS = "/cabinet/+/+/status";
    // 카메라 상태 : /room/{controllerId}/{roomNumber}/camera/status
    public static final String CAMERA_STATUS = "/room/+/+/camera/status";
    //TODO : 토픽 수정
    public static final String VOICE_LOG = "/room/+/voice";
    //TODO : 토픽 수정
    public static final String RUMMIKUB_LOG = "/room/+/rummikub";
    // /cabinet/{controllerId}/card
    public static final String RFID_CARD = "/cabinet/+/card";
    //wake word 상태 : finish / call로 들어온다
    public static final String WAKE_STATUS = "/room/+/wake/status";
    // QnA 서버가 준비되면 알림
    public static final String QNA_READY = "/room/+/qna/ready";
    // QnA 서버에서 req / res를 서버에 전달 -> 로그 저장용
    public static final String QNA_RES = "/room/+/qna/res";
    // 진행자가 파악한 루미큐브 마지막 테이블 상태
    public static final String MC_TURN_LOG = "/room/+/mc/event/turn-log";
    // 진행자가 봤을 때 규칙 위반일 때 알림
    public static final String MC_VIOLATION = "/room/+/mc/event/violation";
}
