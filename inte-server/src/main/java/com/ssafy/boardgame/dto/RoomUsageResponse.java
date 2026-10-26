package com.ssafy.boardgame.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * 룸 이용 이력. roomStatus 는 room_usage 컬럼이 아니라 같은 트랜잭션에서 갱신된
 * room.status 를 서비스가 채워 주는 값이다(입실 USE / 퇴실 EMPTY).
 * endTime 이 null 이면 아직 이용 중인 건이다.
 */
@Getter
@Setter
@NoArgsConstructor
public class RoomUsageResponse {

    private Long roomUsageId;
    private String roomNumber;
    private LocalDateTime startTime;
    private LocalDateTime endTime;
    private String roomStatus;
}
