package com.ssafy.boardgame.mqtt.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.List;

/**
 * 진행자가 읽은 테이블 상태 페이로드 (/room/{roomNumber}/mc/event/turn-log).
 * <p>
 * table 은 세트의 목록이고 세트는 타일의 목록이다 - 바깥 순서가 테이블 위 세트 순서,
 * 안쪽 순서가 세트 안 타일 순서다. 둘 다 의미가 있으므로 순서를 보존해야 한다.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class McTurnLogEvent {
    /** mc/cmd/start 로 내려보낸 게임 세션 식별자 */
    private String sessionId;
    /** 마지막 테이블 상태 */
    private List<List<McTile>> table;
}
