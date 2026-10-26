package com.ssafy.boardgame.service;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.dto.BoardGameItem;
import com.ssafy.boardgame.dto.RentRequest;
import com.ssafy.boardgame.dto.RentResponse;
import com.ssafy.boardgame.dto.RoomResponse;
import com.ssafy.boardgame.mapper.BoardGameItemMapper;
import com.ssafy.boardgame.mapper.BoardGameMapper;
import com.ssafy.boardgame.mapper.RentMapper;
import com.ssafy.boardgame.mapper.ReservationMapper;
import com.ssafy.boardgame.mapper.RoomMapper;
import com.ssafy.boardgame.mqtt.MqttPublisher;
import com.ssafy.boardgame.util.StatusUtil;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InOrder;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;

@ExtendWith(MockitoExtension.class)
@DisplayName("RentService - 보드게임 대여")
class RentServiceTest {

    private static final Long GAME_ID = 1L;
    private static final String GAME_NAME = "루미큐브";
    private static final String ROOM = "A1";

    @Mock private BoardGameMapper boardGameMapper;
    @Mock private BoardGameItemMapper boardGameItemMapper;
    @Mock private RentMapper rentMapper;
    @Mock private RoomMapper roomMapper;
    @Mock private ReservationMapper reservationMapper;
    @Mock private MqttPublisher mqttPublisher;
    @Mock private ReservationNotifyService reservationNotifyService;

    @InjectMocks private RentService rentService;

    private static RentRequest request() {
        RentRequest request = new RentRequest();
        request.setBoardGameId(GAME_ID);
        request.setRoomNumber(ROOM);
        return request;
    }

    private static RoomResponse room(String status) {
        RoomResponse room = new RoomResponse();
        room.setRoomNumber(ROOM);
        room.setCapacity(6);
        room.setStatus(status);
        return room;
    }

    private static BoardGameItem item(Long itemId, Long cabinetId) {
        BoardGameItem item = new BoardGameItem();
        item.setItemId(itemId);
        item.setBoardGameId(GAME_ID);
        item.setCabinetId(cabinetId);
        item.setStatus(StatusUtil.STATUS_BOARD_AVAILABLE);
        return item;
    }

    /** 대여가 성공하는 조건을 전부 갖춘 상태 */
    private void givenRentable() {
        given(boardGameMapper.findNameById(GAME_ID)).willReturn(GAME_NAME);
        given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(StatusUtil.STATUS_ROOM_USE));
        given(rentMapper.countActiveRent(ROOM, GAME_ID)).willReturn(0);
        given(boardGameItemMapper.findAvailableItemForUpdate(GAME_ID)).willReturn(item(10L, 3L));
    }

    @Test
    @DisplayName("대여에 성공하면 선점한 사본 정보가 담긴 응답을 돌려준다")
    void rent_success_returnsRentedItem() {
        givenRentable();

        RentResponse response = rentService.rent(request());

        assertThat(response.getBoardGameId()).isEqualTo(GAME_ID);
        assertThat(response.getBoardGameName()).isEqualTo(GAME_NAME);
        assertThat(response.getBoardGameItemId()).isEqualTo(10L);
        // cabinetId 는 후속 MQTT 캐비넷 오픈에서 그대로 쓰이므로 응답에 반드시 실려야 한다.
        assertThat(response.getCabinetId()).isEqualTo(3L);
        assertThat(response.getRoomNumber()).isEqualTo(ROOM);
    }

    @Test
    @DisplayName("사본을 RENTED 로 바꾼 뒤 대여 이력을 남긴다")
    void rent_success_marksItemRentedThenInsertsHistory() {
        givenRentable();

        RentResponse response = rentService.rent(request());

        InOrder inOrder = inOrder(boardGameItemMapper, rentMapper);
        inOrder.verify(boardGameItemMapper).updateStatus(10L, StatusUtil.STATUS_BOARD_RENTED);
        inOrder.verify(rentMapper).insert(response);
    }

    @Test
    @DisplayName("존재하지 않는 보드게임이면 BOARD_GAME_NOT_FOUND")
    void rent_unknownBoardGame_throwsBoardGameNotFound() {
        given(boardGameMapper.findNameById(GAME_ID)).willReturn(null);

        assertThatThrownBy(() -> rentService.rent(request()))
                .isInstanceOf(BusinessException.class)
                .extracting(e -> ((BusinessException) e).getErrorCode())
                .isEqualTo(ErrorCode.BOARD_GAME_NOT_FOUND);

        // 게임 검증이 방 조회보다 앞서야 불필요한 쿼리가 나가지 않는다.
        then(roomMapper).should(never()).findByRoomNumber(anyString());
    }

    @Test
    @DisplayName("존재하지 않는 방이면 ROOM_NOT_FOUND")
    void rent_unknownRoom_throwsRoomNotFound() {
        given(boardGameMapper.findNameById(GAME_ID)).willReturn(GAME_NAME);
        given(roomMapper.findByRoomNumber(ROOM)).willReturn(null);

        assertThatThrownBy(() -> rentService.rent(request()))
                .isInstanceOf(BusinessException.class)
                .extracting(e -> ((BusinessException) e).getErrorCode())
                .isEqualTo(ErrorCode.ROOM_NOT_FOUND);
    }

    @Test
    @DisplayName("방이 사용 중이 아니면 ROOM_NOT_IN_USE (존재하는 방이므로 404 가 아니다)")
    void rent_roomNotInUse_throwsRoomNotInUse() {
        given(boardGameMapper.findNameById(GAME_ID)).willReturn(GAME_NAME);
        given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(StatusUtil.STATUS_ROOM_EMPTY));

        assertThatThrownBy(() -> rentService.rent(request()))
                .isInstanceOf(BusinessException.class)
                .extracting(e -> ((BusinessException) e).getErrorCode())
                .isEqualTo(ErrorCode.ROOM_NOT_IN_USE);

        then(boardGameItemMapper).should(never()).findAvailableItemForUpdate(anyLong());
    }

    @Test
    @DisplayName("같은 방에서 같은 게임을 이미 대여 중이면 ALREADY_RENTED")
    void rent_alreadyRentedInSameRoom_throwsAlreadyRented() {
        given(boardGameMapper.findNameById(GAME_ID)).willReturn(GAME_NAME);
        given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(StatusUtil.STATUS_ROOM_USE));
        given(rentMapper.countActiveRent(ROOM, GAME_ID)).willReturn(1);

        assertThatThrownBy(() -> rentService.rent(request()))
                .isInstanceOf(BusinessException.class)
                .extracting(e -> ((BusinessException) e).getErrorCode())
                .isEqualTo(ErrorCode.ALREADY_RENTED);

        then(boardGameItemMapper).should(never()).findAvailableItemForUpdate(anyLong());
    }

    @Test
    @DisplayName("대여 가능한 사본이 없으면 BOARD_GAME_OUT_OF_STOCK 이고 이력도 남기지 않는다")
    void rent_noAvailableItem_throwsOutOfStock() {
        given(boardGameMapper.findNameById(GAME_ID)).willReturn(GAME_NAME);
        given(roomMapper.findByRoomNumber(ROOM)).willReturn(room(StatusUtil.STATUS_ROOM_USE));
        given(rentMapper.countActiveRent(ROOM, GAME_ID)).willReturn(0);
        // SKIP LOCKED 로 다른 트랜잭션이 마지막 사본을 잡아간 경우도 여기로 들어온다.
        given(boardGameItemMapper.findAvailableItemForUpdate(GAME_ID)).willReturn(null);

        assertThatThrownBy(() -> rentService.rent(request()))
                .isInstanceOf(BusinessException.class)
                .extracting(e -> ((BusinessException) e).getErrorCode())
                .isEqualTo(ErrorCode.BOARD_GAME_OUT_OF_STOCK);

        then(boardGameItemMapper).should(never()).updateStatus(anyLong(), anyString());
        then(rentMapper).should(never()).insert(any(RentResponse.class));
    }
}
