package com.ssafy.boardgame.service;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.dto.BoardGameDetailResponse;
import com.ssafy.boardgame.dto.BoardGameListResponse;
import com.ssafy.boardgame.dto.BoardGameSearchCondition;
import com.ssafy.boardgame.mapper.BoardGameMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class BoardGameService {

    private final BoardGameMapper boardGameMapper;

    /** 전체검색 + 조건검색. 조건이 비어 있으면 전체 목록이 나온다. */
    public List<BoardGameListResponse> search(BoardGameSearchCondition condition) {
        return boardGameMapper.search(condition);
    }

    public BoardGameDetailResponse findDetail(Long boardGameId) {
        BoardGameDetailResponse detail = boardGameMapper.findDetailById(boardGameId);
        if (detail == null) {
            throw new BusinessException(ErrorCode.BOARD_GAME_NOT_FOUND);
        }
        return detail;
    }
}
