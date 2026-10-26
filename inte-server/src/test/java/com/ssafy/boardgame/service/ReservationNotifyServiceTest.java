package com.ssafy.boardgame.service;

import com.ssafy.boardgame.dto.ReservationResponse;
import com.ssafy.boardgame.mapper.BoardGameItemMapper;
import com.ssafy.boardgame.mapper.ReservationMapper;
import com.ssafy.boardgame.mqtt.MqttPublisher;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.never;

@ExtendWith(MockitoExtension.class)
@DisplayName("ReservationNotifyService - 예약 반납 알림")
class ReservationNotifyServiceTest {

    private static final Long GAME_ID = 1L;
    private static final String GAME_NAME = "루미큐브";
    private static final String FIRST_ROOM = "A1";
    private static final String SECOND_ROOM = "A2";
    private static final Long FIRST_RESERVATION = 10L;
    private static final Long SECOND_RESERVATION = 11L;
    private static final int TIMEOUT_SEC = 60;

    @Mock private ReservationMapper reservationMapper;
    @Mock private BoardGameItemMapper boardGameItemMapper;
    @Mock private MqttPublisher mqttPublisher;
    @Mock private ScheduledExecutorService delayedTaskScheduler;

    @InjectMocks private ReservationNotifyService reservationNotifyService;

    @BeforeEach
    void setUp() {
        // @Value 는 스프링 컨텍스트 없이는 주입되지 않는다
        ReflectionTestUtils.setField(reservationNotifyService, "popupTimeoutSec", TIMEOUT_SEC);
    }

    private static ReservationResponse waiting(Long reservationId, String roomNumber) {
        ReservationResponse reservation = new ReservationResponse();
        reservation.setReservationId(reservationId);
        reservation.setBoardGameId(GAME_ID);
        reservation.setBoardGameName(GAME_NAME);
        reservation.setRoomNumber(roomNumber);
        return reservation;
    }

    /** 재고가 있고 1등이 기다리는, 알림이 나가야 하는 상황 */
    private void givenFirstWaiter() {
        given(boardGameItemMapper.countAvailable(GAME_ID)).willReturn(1);
        given(reservationMapper.findFirstWaiting(GAME_ID))
                .willReturn(waiting(FIRST_RESERVATION, FIRST_ROOM));
    }

    /**
     * 스케줄러에 등록된 타임아웃 작업을 꺼내 즉시 실행한다.
     * 60초를 실제로 기다리지 않고 무응답 상황만 재현한다.
     */
    private void runScheduledTimeout() {
        ArgumentCaptor<Runnable> task = ArgumentCaptor.forClass(Runnable.class);
        then(delayedTaskScheduler).should()
                .schedule(task.capture(), eq((long) TIMEOUT_SEC), eq(TimeUnit.SECONDS));
        task.getValue().run();
    }

    @Nested
    @DisplayName("알림 발행")
    class Notify {

        @Test
        @DisplayName("가장 먼저 예약한 방에게만 발행하고 타임아웃을 건다")
        void notify_firstWaiterOnly() {
            givenFirstWaiter();

            reservationNotifyService.notifyFirstWaiting(GAME_ID);

            then(mqttPublisher).should()
                    .reservationReady(FIRST_ROOM, FIRST_RESERVATION, GAME_ID, GAME_NAME, TIMEOUT_SEC);
            then(delayedTaskScheduler).should()
                    .schedule(any(Runnable.class), eq((long) TIMEOUT_SEC), eq(TimeUnit.SECONDS));
        }

        @Test
        @DisplayName("응답을 기다리는 팝업이 있으면 두 번째 반납에도 발행하지 않는다")
        void notify_alreadyPending_doesNotPublishAgain() {
            givenFirstWaiter();
            reservationNotifyService.notifyFirstWaiting(GAME_ID);

            // 사본이 한 벌 더 돌아와도 알림은 여전히 한 방에게만 나가 있어야 한다
            reservationNotifyService.notifyFirstWaiting(GAME_ID);

            then(mqttPublisher).should()
                    .reservationReady(FIRST_ROOM, FIRST_RESERVATION, GAME_ID, GAME_NAME, TIMEOUT_SEC);
            then(mqttPublisher).shouldHaveNoMoreInteractions();
        }

        @Test
        @DisplayName("재고가 없으면 대기자를 찾지도 않는다")
        void notify_noStock_doesNothing() {
            given(boardGameItemMapper.countAvailable(GAME_ID)).willReturn(0);

            reservationNotifyService.notifyFirstWaiting(GAME_ID);

            then(reservationMapper).should(never()).findFirstWaiting(anyLong());
            then(mqttPublisher).shouldHaveNoInteractions();
        }

        @Test
        @DisplayName("대기자가 없으면 발행하지 않는다")
        void notify_noWaiter_doesNotPublish() {
            given(boardGameItemMapper.countAvailable(GAME_ID)).willReturn(1);
            given(reservationMapper.findFirstWaiting(GAME_ID)).willReturn(null);

            reservationNotifyService.notifyFirstWaiting(GAME_ID);

            then(mqttPublisher).shouldHaveNoInteractions();
            then(delayedTaskScheduler).shouldHaveNoInteractions();
        }

        @Test
        @DisplayName("boardGameId 가 null 이면 아무것도 하지 않는다")
        void notify_nullGame_doesNothing() {
            reservationNotifyService.notifyFirstWaiting(null);

            then(boardGameItemMapper).shouldHaveNoInteractions();
            then(mqttPublisher).shouldHaveNoInteractions();
        }
    }

    @Nested
    @DisplayName("팝업 응답 (resolve)")
    class Resolve {

        @Test
        @DisplayName("응답한 방이 기다리던 방이면 타임아웃이 예약을 건드리지 않는다")
        void resolve_thenTimeout_doesNotCancel() {
            givenFirstWaiter();
            reservationNotifyService.notifyFirstWaiting(GAME_ID);

            reservationNotifyService.resolve(GAME_ID, FIRST_ROOM);
            runScheduledTimeout();

            then(reservationMapper).should(never()).cancel(anyLong());
        }

        @Test
        @DisplayName("다른 방의 응답은 팝업을 놓아 주지 않는다")
        void resolve_otherRoom_keepsPending() {
            givenFirstWaiter();
            reservationNotifyService.notifyFirstWaiting(GAME_ID);

            // 2등이 새로고침해서 먼저 빌려도 1등의 팝업은 살아 있어야 한다
            reservationNotifyService.resolve(GAME_ID, SECOND_ROOM);

            // 재고가 남아 있는 상태로 타임아웃이 오면 1등 예약이 취소된다 = 팝업이 유지됐다는 뜻
            given(reservationMapper.findFirstWaiting(GAME_ID)).willReturn(null);
            runScheduledTimeout();

            then(reservationMapper).should().cancel(FIRST_RESERVATION);
        }
    }

    @Nested
    @DisplayName("무응답 타임아웃")
    class Timeout {

        @Test
        @DisplayName("무응답이면 예약을 취소하고 다음 대기자에게 넘긴다")
        void timeout_cancelsAndNotifiesNext() {
            givenFirstWaiter();
            reservationNotifyService.notifyFirstWaiting(GAME_ID);

            // 1등이 취소된 뒤에는 2등이 첫 대기자가 된다
            given(reservationMapper.findFirstWaiting(GAME_ID))
                    .willReturn(waiting(SECOND_RESERVATION, SECOND_ROOM));
            runScheduledTimeout();

            then(reservationMapper).should().cancel(FIRST_RESERVATION);
            then(mqttPublisher).should()
                    .reservationReady(SECOND_ROOM, SECOND_RESERVATION, GAME_ID, GAME_NAME, TIMEOUT_SEC);
        }

        @Test
        @DisplayName("그 사이 재고가 나갔으면 누를 기회가 없었으므로 예약을 유지한다")
        void timeout_stockGone_keepsReservation() {
            givenFirstWaiter();
            reservationNotifyService.notifyFirstWaiting(GAME_ID);

            // 팝업이 떠 있는 동안 다른 방이 가져갔다
            given(boardGameItemMapper.countAvailable(GAME_ID)).willReturn(0);
            runScheduledTimeout();

            then(reservationMapper).should(never()).cancel(anyLong());
        }

        @Test
        @DisplayName("타임아웃으로 팝업이 풀리면 같은 게임에 다시 알림을 보낼 수 있다")
        void timeout_releasesPending() {
            givenFirstWaiter();
            reservationNotifyService.notifyFirstWaiting(GAME_ID);
            given(reservationMapper.findFirstWaiting(GAME_ID)).willReturn(null);
            runScheduledTimeout();

            // 다음 반납 때 2등이 정상적으로 알림을 받는다
            given(reservationMapper.findFirstWaiting(GAME_ID))
                    .willReturn(waiting(SECOND_RESERVATION, SECOND_ROOM));
            reservationNotifyService.notifyFirstWaiting(GAME_ID);

            then(mqttPublisher).should()
                    .reservationReady(SECOND_ROOM, SECOND_RESERVATION, GAME_ID, GAME_NAME, TIMEOUT_SEC);
        }
    }
}
