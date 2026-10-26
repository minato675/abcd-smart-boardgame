package com.ssafy.boardgame.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * 보드게임 목록/검색 조건. 세 값 모두 null 이면 전체 조회가 된다.
 * 페이징이 필요해지면 page/size 를 여기에 추가한다.
 */
@Getter
@Setter
@NoArgsConstructor
@Schema(description = "보드게임 검색 조건. 세 값 모두 비우면 전체 조회가 된다.")
public class BoardGameSearchCondition {

    /** 보드게임명 부분 일치 (대소문자 무시) */
    @Schema(description = "보드게임명 부분 일치 (대소문자 무시)", example = "루미")
    private String keyword;

    /** 카테고리 ID */
    @Schema(description = "카테고리 ID", example = "1")
    private Long categoryId;

    /** 플레이 인원 (min_players ~ max_players 범위에 포함되는 게임만) */
    @Schema(description = "플레이 인원. min_players ~ max_players 범위에 포함되는 게임만 반환한다.", example = "4")
    private Integer players;
}
