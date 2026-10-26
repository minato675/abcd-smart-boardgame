package com.ssafy.boardgame.controller;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.dto.BoardGameDetailResponse;
import com.ssafy.boardgame.dto.BoardGameListResponse;
import com.ssafy.boardgame.dto.BoardGameSearchCondition;
import com.ssafy.boardgame.dto.CategoryResponse;
import com.ssafy.boardgame.service.BoardGameService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.BDDMockito.willThrow;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BoardGameController.class)
@DisplayName("BoardGameController - 보드게임 조회 API")
class BoardGameControllerTest {

    @Autowired private MockMvc mockMvc;

    @MockitoBean private BoardGameService boardGameService;

    private static BoardGameListResponse listItem(Long id, String name) {
        BoardGameListResponse item = new BoardGameListResponse();
        item.setBoardGameId(id);
        item.setName(name);
        item.setMinPlayers(2);
        item.setMaxPlayers(4);
        item.setDifficulty("NORMAL");
        item.setPlayTime(60);
        item.setTotalCount(3);
        item.setAvailableCount(1);
        item.setCategories(List.of(category(1L, "전략")));
        return item;
    }

    private static CategoryResponse category(Long id, String name) {
        CategoryResponse category = new CategoryResponse();
        category.setCategoryId(id);
        category.setName(name);
        return category;
    }

    @Nested
    @DisplayName("GET /boardgame - 검색")
    class Search {

        @Test
        @DisplayName("파라미터가 없으면 전체 목록을 반환한다")
        void search_noParams_returnsAll() throws Exception {
            given(boardGameService.search(any(BoardGameSearchCondition.class)))
                    .willReturn(List.of(listItem(1L, "루미큐브"), listItem(2L, "할리갈리")));

            mockMvc.perform(get("/boardgame"))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.length()").value(2))
                    .andExpect(jsonPath("$[0].boardGameId").value(1))
                    .andExpect(jsonPath("$[0].name").value("루미큐브"))
                    .andExpect(jsonPath("$[0].totalCount").value(3))
                    .andExpect(jsonPath("$[0].availableCount").value(1))
                    .andExpect(jsonPath("$[0].categories[0].name").value("전략"));
        }

        @Test
        @DisplayName("keyword/categoryId/players 가 조건 객체에 바인딩된다")
        void search_bindsAllConditionParams() throws Exception {
            given(boardGameService.search(any(BoardGameSearchCondition.class)))
                    .willReturn(List.of());

            mockMvc.perform(get("/boardgame")
                            .param("keyword", "루미")
                            .param("categoryId", "1")
                            .param("players", "4"))
                    .andExpect(status().isOk());

            ArgumentCaptor<BoardGameSearchCondition> captor =
                    ArgumentCaptor.forClass(BoardGameSearchCondition.class);
            then(boardGameService).should().search(captor.capture());
            assertThat(captor.getValue().getKeyword()).isEqualTo("루미");
            assertThat(captor.getValue().getCategoryId()).isEqualTo(1L);
            assertThat(captor.getValue().getPlayers()).isEqualTo(4);
        }

        @Test
        @DisplayName("일부 조건만 줘도 나머지는 null 로 남는다")
        void search_partialParams_leavesOthersNull() throws Exception {
            given(boardGameService.search(any(BoardGameSearchCondition.class)))
                    .willReturn(List.of());

            mockMvc.perform(get("/boardgame").param("keyword", "루미"))
                    .andExpect(status().isOk());

            ArgumentCaptor<BoardGameSearchCondition> captor =
                    ArgumentCaptor.forClass(BoardGameSearchCondition.class);
            then(boardGameService).should().search(captor.capture());
            assertThat(captor.getValue().getKeyword()).isEqualTo("루미");
            assertThat(captor.getValue().getCategoryId()).isNull();
            assertThat(captor.getValue().getPlayers()).isNull();
        }

        @Test
        @DisplayName("결과가 없으면 200 과 빈 배열이다 (404 가 아니다)")
        void search_noMatch_returnsEmptyArray() throws Exception {
            given(boardGameService.search(any(BoardGameSearchCondition.class)))
                    .willReturn(List.of());

            mockMvc.perform(get("/boardgame").param("keyword", "없는게임"))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.length()").value(0));
        }
    }

    @Nested
    @DisplayName("GET /boardgame/{boardGameId} - 상세")
    class Detail {

        @Test
        @DisplayName("상세 조회에 성공하면 200 과 상세 필드를 반환한다")
        void detail_success_returns200() throws Exception {
            BoardGameDetailResponse detail = new BoardGameDetailResponse();
            detail.setBoardGameId(1L);
            detail.setName("루미큐브");
            detail.setMinPlayers(2);
            detail.setMaxPlayers(4);
            detail.setDifficulty("NORMAL");
            detail.setPlayTime(60);
            detail.setDescription("숫자 타일 게임");
            detail.setHowToPlay("30점 이상으로 등록한다");
            detail.setTotalCount(3);
            detail.setAvailableCount(0);
            detail.setWaitingCount(2);
            detail.setCategories(List.of(category(1L, "전략")));
            given(boardGameService.findDetail(1L)).willReturn(detail);

            mockMvc.perform(get("/boardgame/1"))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.boardGameId").value(1))
                    .andExpect(jsonPath("$.name").value("루미큐브"))
                    .andExpect(jsonPath("$.description").value("숫자 타일 게임"))
                    .andExpect(jsonPath("$.howToPlay").value("30점 이상으로 등록한다"))
                    .andExpect(jsonPath("$.waitingCount").value(2))
                    .andExpect(jsonPath("$.categories[0].categoryId").value(1));
        }

        @Test
        @DisplayName("카테고리가 없는 게임은 빈 배열로 나온다")
        void detail_noCategories_returnsEmptyArray() throws Exception {
            BoardGameDetailResponse detail = new BoardGameDetailResponse();
            detail.setBoardGameId(2L);
            detail.setName("카테고리없음");
            given(boardGameService.findDetail(2L)).willReturn(detail);

            mockMvc.perform(get("/boardgame/2"))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.categories.length()").value(0));
        }

        @Test
        @DisplayName("존재하지 않는 보드게임이면 404 BOARD_GAME_NOT_FOUND")
        void detail_unknownId_returns404() throws Exception {
            willThrow(new BusinessException(ErrorCode.BOARD_GAME_NOT_FOUND))
                    .given(boardGameService).findDetail(999L);

            mockMvc.perform(get("/boardgame/999"))
                    .andExpect(status().isNotFound())
                    .andExpect(jsonPath("$.code").value("BOARD_GAME_NOT_FOUND"))
                    .andExpect(jsonPath("$.message").value("존재하지 않는 보드게임입니다."));
        }

        @Test
        @DisplayName("숫자가 아닌 ID 는 400 이다")
        void detail_nonNumericId_returns400() throws Exception {
            mockMvc.perform(get("/boardgame/abc"))
                    .andExpect(status().isBadRequest());
        }
    }
}
