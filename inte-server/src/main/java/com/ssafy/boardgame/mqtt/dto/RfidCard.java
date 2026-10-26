package com.ssafy.boardgame.mqtt.dto;

import lombok.*;

@Getter
@Setter
@NoArgsConstructor
public class RfidCard {
    private String transactionId;
    private String cardUid;
}
