package com.ssafy.boardgame.mqtt.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * 루미큐브 타일 한 장.
 * <p>
 * 진행자는 number 를 문자열("1")로 실어 보내지만 Jackson 이 int 로 변환해 준다.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class McTile {
    /** 타일 색 */
    private String color;
    /** 타일 번호. 조커는 0 이다. */
    private int number;
}
