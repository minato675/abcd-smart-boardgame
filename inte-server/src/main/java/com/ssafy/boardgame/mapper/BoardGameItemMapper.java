package com.ssafy.boardgame.mapper;

import com.ssafy.boardgame.dto.BoardGameItem;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

@Mapper
public interface BoardGameItemMapper {
    List<Map<String, Object>> findAll();

    /**
     * 대여 가능한 사본 1개를 잠그고 가져온다 (없으면 null).
     * SKIP LOCKED 이므로 다른 트랜잭션이 잡고 있는 행은 건너뛴다.
     */
    BoardGameItem findAvailableItemForUpdate(@Param("boardGameId") Long boardGameId);

    void updateStatus(@Param("itemId") Long itemId, @Param("status") String status);

    int countAvailable(@Param("boardGameId") Long boardGameId);

    /**
     * 퇴실 정리용. 해당 방이 대여 중인 사본을 모두 AVAILABLE 로 되돌린다.
     * 대상을 rent.returned_at IS NULL 로 찾으므로 RentMapper.returnAllByRoom 보다 먼저 호출해야 한다.
     */
    int releaseByRoom(@Param("roomNumber") String roomNumber);
}
