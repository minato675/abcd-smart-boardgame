package com.ssafy.boardgame.mapper;

import com.ssafy.boardgame.dto.RoomUsageResponse;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface RoomUsageMapper {

    /** 이용 중(end_time IS NULL)인 건이 없을 때만 새 이용 이력을 만든다. 반환값은 삽입된 행 수(0 또는 1). */
    int insertIfAbsent(@Param("roomNumber") String roomNumber);

    /** 이용 중인 건의 end_time 을 현재시간으로 닫는다. 반환값은 닫힌 행 수(0 또는 1). */
    int closeByRoom(@Param("roomNumber") String roomNumber);

    /** 이용 중인 건. 없으면 null. */
    RoomUsageResponse findOpenByRoom(@Param("roomNumber") String roomNumber);

    /** 종료 여부와 무관하게 가장 최근 이용 건. 없으면 null. */
    RoomUsageResponse findLatestByRoom(@Param("roomNumber") String roomNumber);
}
