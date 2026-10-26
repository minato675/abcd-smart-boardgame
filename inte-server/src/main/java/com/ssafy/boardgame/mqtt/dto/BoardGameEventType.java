package com.ssafy.boardgame.mqtt.dto;

/** /boardgame/event 페이로드의 type. 재고(availableCount)를 바꾸는 두 전이만 있다. */
public enum BoardGameEventType {
    RENT,
    RETURN
}
