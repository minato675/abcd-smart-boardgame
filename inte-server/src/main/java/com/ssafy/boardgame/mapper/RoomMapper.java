package com.ssafy.boardgame.mapper;

import com.ssafy.boardgame.dto.RoomResponse;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface RoomMapper {

    RoomResponse findByRoomNumber(@Param("roomNumber") String roomNumber);
    int updateRoomStatus(@Param("roomNumber") String roomNumber,
                                  @Param("status") String status);

    String findRoomByRfid(@Param("rfid") String rfid);
}
