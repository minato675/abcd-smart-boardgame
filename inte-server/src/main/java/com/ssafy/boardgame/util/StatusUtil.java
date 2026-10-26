package com.ssafy.boardgame.util;

public class StatusUtil {
    //보드게임 상태
    public static final String STATUS_BOARD_RENTED = "rented";
    public static final String STATUS_BOARD_AVAILABLE = "available";
    //예약 상태
    public static final String STATUS_RESERVATION_WAITING = "waiting";
    public static final String STATUS_RESERVATION_FULFILLED = "fulfilled";
    public static final String STATUS_RESERVATION_CANCELLED = "cancelled";
    //룸 상태
    public static final String STATUS_ROOM_USE = "use";
    public static final String STATUS_ROOM_EMPTY = "empty";
    //사물함 상태 (cabinet.status)
    public static final String STATUS_CABINET_OPEN = "open";
    public static final String STATUS_CABINET_CLOSED = "closed";
    //사물함 이력 이벤트 (cabinet_history.event_type). 상태값과 달리 닫힘이 CLOSE 다.
    public static final String CABINET_EVENT_OPEN = "open";
    public static final String CABINET_EVENT_CLOSE = "close";
    //사물함 이력 발생 주체 (cabinet_history.triggered_by)
    public static final String CABINET_TRIGGERED_BY_USER = "user";
    //대여 상태 (rent.status)
    public static final String STATUS_RENT_RENT = "rent";
    public static final String STATUS_RENT_USING = "using";
    public static final String STATUS_RENT_RETURNED = "returned";
    //사물함 오픈 사유
    public static final String CABINET_OPEN_MODE_RETURN = "return";
    public static final String CABINET_OPEN_MODE_RECEIVE = "receive";
    //wake word 상태 (/room/+/wake/status)
    public static final String STATUS_WAKE_CALL = "call";
    public static final String STATUS_WAKE_FINISH = "finish";
}
