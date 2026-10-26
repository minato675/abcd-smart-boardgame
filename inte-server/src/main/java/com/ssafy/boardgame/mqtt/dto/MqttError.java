package com.ssafy.boardgame.mqtt.dto;

import lombok.*;

/**
 * 컨트롤러에게 보내는 실패 응답.
 * code 는 {@link com.ssafy.boardgame.common.ErrorCode} 이름을 그대로 넣어, 하드웨어가 사유별로 분기할 수 있게 한다.
 * message 는 사람이 읽는 용도라 하드웨어가 분기 조건으로 쓰면 안 된다.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class MqttError {
    private String transactionId;
    private String code;
    private String message;
}
