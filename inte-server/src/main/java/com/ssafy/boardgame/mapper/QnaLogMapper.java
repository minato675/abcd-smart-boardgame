package com.ssafy.boardgame.mapper;

import com.ssafy.boardgame.dto.QnaLog;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface QnaLogMapper {

    /** 성공 시 파라미터 객체의 qnaLogId/createdAt 이 채워진다. */
    int insert(QnaLog qnaLog);
}
