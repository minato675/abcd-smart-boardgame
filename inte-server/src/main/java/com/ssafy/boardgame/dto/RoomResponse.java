package com.ssafy.boardgame.dto;

import lombok.*;

@Getter
@Setter
@NoArgsConstructor
public class RoomResponse {
    private String roomNumber;
    private int capacity;
    private String status;
}
