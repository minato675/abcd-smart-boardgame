package com.ssafy.boardgame.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * 대여 결과. cabinetId 는 후속 단계(MQTT 캐비넷 오픈)에서 그대로 사용한다.
 */
@Getter
@Setter
@NoArgsConstructor
public class RentResponse {

    private Long rentId;
    private Long boardGameId;
    private String boardGameName;
    private Long boardGameItemId;
    private Long cabinetId;
    private String roomNumber;
    private LocalDateTime rentedAt;

    public static RentResponse of(Long boardGameId, String boardGameName,
                                  BoardGameItem item, String roomNumber) {
        RentResponse response = new RentResponse();
        response.boardGameId = boardGameId;
        response.boardGameName = boardGameName;
        response.boardGameItemId = item.getItemId();
        response.cabinetId = item.getCabinetId();
        response.roomNumber = roomNumber;
        return response;
    }
}
