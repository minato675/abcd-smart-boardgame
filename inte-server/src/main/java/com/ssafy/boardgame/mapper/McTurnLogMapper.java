package com.ssafy.boardgame.mapper;

import com.ssafy.boardgame.dto.McTurnLog;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface McTurnLogMapper {

    /**
     * 성공 시 파라미터 객체의 turnLogId/turnNo/createdAt 이 채워진다.
     * turnNo 는 넘기지 않는다 - 같은 세션의 기존 행에서 이어서 매긴다.
     */
    int insert(McTurnLog turnLog);

    /** 한 세션의 테이블 기록을 턴 순서대로. 없으면 빈 리스트. */
    List<McTurnLog> findBySession(@Param("sessionId") String sessionId);

    /**
     * 한 세션에서 가장 마지막 턴. 아직 기록이 없으면 null.
     * <p>
     * '이전 화면 보기' 가 쓰는 조회다. turn_no 가 매퍼에서 순증하므로 그 최대값이
     * 곧 마지막으로 생성된 행이다.
     */
    McTurnLog findLatestBySession(@Param("sessionId") String sessionId);
}
