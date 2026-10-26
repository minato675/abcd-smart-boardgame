package com.ssafy.boardgame.mqtt.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * /boardgame/event 페이로드.
 * <p>
 * 대여/반납으로 어떤 보드게임의 재고(availableCount)가 바뀌었다는 방송이다. 방을 가리지
 * 않고 모든 태블릿에 나간다 - 다른 방의 대여/반납도 이 방의 목록 화면 재고에 영향을 준다.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class BoardGameEvent {

    private BoardGameEventType type;
    private Long boardGameId;
    /** 이 전이를 일으킨 방. 태블릿이 자기 방이 한 일인지 구분해야 할 때를 위해 싣는다. */
    private String roomNumber;
}
