package com.ssafy.boardgame.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.ArrayList;
import java.util.List;

/**
 * 보드게임 목록 항목.
 * totalCount/availableCount 는 board_game_item 기준 보유/대여가능 사본 수.
 */
@Getter
@Setter
@NoArgsConstructor
public class BoardGameListResponse {

    private Long boardGameId;
    private String name;
    private Integer minPlayers;
    private Integer maxPlayers;
    private String difficulty;
    private Integer playTime;
    private String imageUrl;
    private String description;

    private int totalCount;
    private int availableCount;

    private List<CategoryResponse> categories = new ArrayList<>();
}
