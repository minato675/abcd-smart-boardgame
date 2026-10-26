package com.ssafy.boardgame.mqtt.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * wake word 상태 페이로드 (/room/{roomNumber}/wake/status).
 * status 는 'call'(호출됨) | 'finish'(종료됨).
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class WakeStatus {
    private String status;
}
