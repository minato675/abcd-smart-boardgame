package com.ssafy.boardgame.mapper;

import com.ssafy.boardgame.dto.McViolationLog;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface McViolationLogMapper {

    /** 성공 시 파라미터 객체의 violationLogId/createdAt 이 채워진다. */
    int insert(McViolationLog violationLog);

    /** 한 세션에서 잡힌 위반을 시간 순서대로. 없으면 빈 리스트. */
    List<McViolationLog> findBySession(@Param("sessionId") String sessionId);
}
