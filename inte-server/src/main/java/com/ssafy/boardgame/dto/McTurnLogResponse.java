package com.ssafy.boardgame.dto;

import com.ssafy.boardgame.mqtt.dto.McTile;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.List;

/**
 * '이전 화면 보기' 응답 - 마지막으로 기록된 테이블 상태.
 * <p>
 * DB 에는 JSONB 문자열로 들어 있지만 여기서는 파싱해서 내려준다. 태블릿이 문자열을
 * 한 번 더 JSON.parse 하지 않아도 되고, 형태가 깨진 기록은 서버에서 먼저 걸러진다.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "마지막으로 기록된 테이블 상태")
public class McTurnLogResponse {

    @Schema(description = "이 세션에서 몇 번째 턴인지", example = "3")
    private Integer turnNo;

    @Schema(description = "테이블에 놓인 타일 총 개수", example = "13")
    private int tileCount;

    @Schema(description = "테이블 상태. 바깥이 세트, 안쪽이 세트 안 타일이며 둘 다 순서가 의미를 갖는다.")
    private List<List<McTile>> table;
}
