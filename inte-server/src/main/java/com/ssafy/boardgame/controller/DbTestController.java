package com.ssafy.boardgame.controller;

import com.ssafy.boardgame.mapper.BoardGameItemMapper;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@Tag(name = "테스트 - DB", description = "DB 연결 확인용 개발 편의 API")
public class DbTestController {

    private final BoardGameItemMapper boardGameItemMapper;

    public DbTestController(BoardGameItemMapper boardGameItemMapper) {
        this.boardGameItemMapper = boardGameItemMapper;
    }

    @Operation(summary = "board_game_item 전체 조회", description = "DB 연결이 살아있는지 확인하기 위해 원본 행을 그대로 반환한다.")
    @GetMapping("/db/test")
    public List<Map<String, Object>> test() {
        return boardGameItemMapper.findAll();
    }
}
