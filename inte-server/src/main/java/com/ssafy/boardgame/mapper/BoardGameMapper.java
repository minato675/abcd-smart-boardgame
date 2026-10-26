package com.ssafy.boardgame.mapper;

import com.ssafy.boardgame.dto.BoardGameDetailResponse;
import com.ssafy.boardgame.dto.BoardGameListResponse;
import com.ssafy.boardgame.dto.BoardGameSearchCondition;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface BoardGameMapper {

    /** 조건이 모두 비어 있으면 전체 목록 */
    List<BoardGameListResponse> search(BoardGameSearchCondition condition);

    BoardGameDetailResponse findDetailById(@Param("boardGameId") Long boardGameId);

    /** 존재 확인 및 응답 메시지용 이름 조회. 없으면 null */
    String findNameById(@Param("boardGameId") Long boardGameId);

    /** 카테고리 매핑 일괄 등록. categoryIds 가 비어 있으면 호출하지 않는다. */
    void insertCategories(@Param("boardGameId") Long boardGameId,
                          @Param("categoryIds") List<Long> categoryIds);

    /**
     * 전달된 카테고리 ID 중 실제 존재하는 개수.
     * board_game_category 에 FK 가 없어 없는 카테고리도 그냥 들어가므로 등록 전에 직접 검증한다.
     */
    int countExistingCategories(@Param("categoryIds") List<Long> categoryIds);
}
