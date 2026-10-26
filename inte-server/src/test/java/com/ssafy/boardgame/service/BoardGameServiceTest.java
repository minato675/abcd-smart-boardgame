package com.ssafy.boardgame.service;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.dto.BoardGameDetailResponse;
import com.ssafy.boardgame.dto.BoardGameListResponse;
import com.ssafy.boardgame.dto.BoardGameSearchCondition;
import com.ssafy.boardgame.mapper.BoardGameMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;

@ExtendWith(MockitoExtension.class)
@DisplayName("BoardGameService - 검색/상세")
class BoardGameServiceTest {

    @Mock private BoardGameMapper boardGameMapper;

    @InjectMocks private BoardGameService boardGameService;

    private static BoardGameListResponse listItem(Long id, String name) {
        BoardGameListResponse item = new BoardGameListResponse();
        item.setBoardGameId(id);
        item.setName(name);
        return item;
    }

    @Test
    @DisplayName("검색 조건을 매퍼에 그대로 위임한다")
    void search_delegatesConditionToMapper() {
        BoardGameSearchCondition condition = new BoardGameSearchCondition();
        condition.setKeyword("루미");
        condition.setCategoryId(1L);
        condition.setPlayers(4);
        List<BoardGameListResponse> expected = List.of(listItem(1L, "루미큐브"));
        given(boardGameMapper.search(condition)).willReturn(expected);

        assertThat(boardGameService.search(condition)).isEqualTo(expected);
        then(boardGameMapper).should().search(condition);
    }

    @Test
    @DisplayName("조건이 비어 있으면 전체 목록이 그대로 나온다")
    void search_emptyCondition_returnsAll() {
        BoardGameSearchCondition condition = new BoardGameSearchCondition();
        given(boardGameMapper.search(condition))
                .willReturn(List.of(listItem(1L, "루미큐브"), listItem(2L, "할리갈리")));

        assertThat(boardGameService.search(condition)).hasSize(2);
    }

    @Test
    @DisplayName("검색 결과가 없으면 빈 목록이다 (예외가 아니다)")
    void search_noMatch_returnsEmptyList() {
        BoardGameSearchCondition condition = new BoardGameSearchCondition();
        condition.setKeyword("없는게임");
        given(boardGameMapper.search(condition)).willReturn(List.of());

        assertThat(boardGameService.search(condition)).isEmpty();
    }

    @Test
    @DisplayName("상세 조회에 성공하면 매퍼 결과를 그대로 반환한다")
    void findDetail_success_returnsDetail() {
        BoardGameDetailResponse detail = new BoardGameDetailResponse();
        detail.setBoardGameId(1L);
        detail.setName("루미큐브");
        given(boardGameMapper.findDetailById(1L)).willReturn(detail);

        assertThat(boardGameService.findDetail(1L)).isSameAs(detail);
    }

    @Test
    @DisplayName("존재하지 않는 보드게임이면 BOARD_GAME_NOT_FOUND")
    void findDetail_unknownId_throwsBoardGameNotFound() {
        given(boardGameMapper.findDetailById(999L)).willReturn(null);

        assertThatThrownBy(() -> boardGameService.findDetail(999L))
                .isInstanceOf(BusinessException.class)
                .extracting(e -> ((BusinessException) e).getErrorCode())
                .isEqualTo(ErrorCode.BOARD_GAME_NOT_FOUND);
    }
}
