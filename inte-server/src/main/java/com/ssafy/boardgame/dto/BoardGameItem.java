package com.ssafy.boardgame.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * board_game_item 한 행 (서비스 내부용).
 */
@Getter
@Setter
@NoArgsConstructor
public class BoardGameItem {

    private Long itemId;
    private Long boardGameId;
    private Long cabinetId;
    private String status;
}
