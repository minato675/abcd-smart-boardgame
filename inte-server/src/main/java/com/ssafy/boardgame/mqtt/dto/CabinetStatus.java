package com.ssafy.boardgame.mqtt.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * /cabinet/{controllerId}/{cabinetNumber}/status 페이로드.
 * status 는 OPEN / CLOSED 두 값만 유효하다.
 */
@Getter
@Setter
@NoArgsConstructor
public class CabinetStatus {
    private String transactionId;
    private int step;
    private String status;
    private String mode;
}
