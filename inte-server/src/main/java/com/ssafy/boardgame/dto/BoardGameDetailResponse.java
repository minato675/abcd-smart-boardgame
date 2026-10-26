package com.ssafy.boardgame.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.ArrayList;
import java.util.List;

/**
 * 보드게임 상세. 목록 필드 + 소개/게임방법 + 현재 예약 대기 팀 수.
 */
@Getter
@Setter
@NoArgsConstructor
public class BoardGameDetailResponse {

    private Long boardGameId;
    private String name;
    private Integer minPlayers;
    private Integer maxPlayers;
    private String difficulty;
    private Integer playTime;
    private String imageUrl;
    private String description;
    private String howToPlay;

    private int totalCount;
    private int availableCount;

    /** 현재 WAITING 상태인 예약 건수 */
    private int waitingCount;

    private List<CategoryResponse> categories = new ArrayList<>();
}
