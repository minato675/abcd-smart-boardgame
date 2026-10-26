package com.ssafy.boardgame.service;

import com.ssafy.boardgame.dto.ReservationResponse;
import com.ssafy.boardgame.mapper.BoardGameItemMapper;
import com.ssafy.boardgame.mapper.ReservationMapper;
import com.ssafy.boardgame.mqtt.MqttPublisher;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * 예약한 게임이 반납됐을 때 대기열의 첫 번째 방에게만 팝업 알림을 보내는 창구.
 * <p>
 * 흐름은 이렇다. 반납 확정 -> 첫 대기자에게 {@code /room/{roomNumber}/reservation/ready} 발행 ->
 * 태블릿 팝업 -> "빌린다" 면 {@code POST /rent}, "안 빌린다" 면 {@code PATCH /reservation/cancel}.
 * 두 응답 모두 기존 API 를 그대로 타므로 여기서는 알림과 타임아웃만 책임진다.
 * <p>
 * <b>왜 타임아웃이 필요한가.</b> 알림을 보내고 아무 상태도 남기지 않으면, 1등이 팝업을 무시했을 때
 * 2등은 그 게임이 <i>다음에 또</i> 반납될 때까지 영영 알림을 못 받는다(매번 그 시점의 1등만 뽑히므로).
 * 그래서 응답을 기다리는 동안 게임을 {@link #pendingNotices} 에 잡아 두고, 시간이 지나면
 * 무응답을 "안 빌린다" 와 같게 처리해 다음 대기자로 넘긴다.
 * <p>
 * 대기 상태를 DB 가 아니라 메모리에 두는 이유는 이것이 팝업 한 번의 수명(1분)만 사는 값이기 때문이다.
 * 서버가 재시작하면 팝업도 같이 사라지므로 복원할 대상이 아니다. 다만 그 사이 예약은 waiting 으로
 * 남아 있어 다음 반납 때 정상적으로 다시 알림을 받는다.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ReservationNotifyService {

    private final ReservationMapper reservationMapper;
    private final BoardGameItemMapper boardGameItemMapper;
    private final MqttPublisher mqttPublisher;
    private final ScheduledExecutorService delayedTaskScheduler;

    /** 팝업을 띄워 두고 응답을 기다리는 시간. 태블릿에도 같은 값을 내려보내 양쪽 타이머를 맞춘다. */
    @Value("${reservation.popup-timeout-sec:60}")
    private int popupTimeoutSec;

    /**
     * 팝업 응답을 기다리는 게임. key 는 boardGameId 다.
     * <p>
     * 게임 단위로 잡는 이유는 "한 게임의 알림은 동시에 한 방에게만" 이 이 기능의 핵심 규칙이라서다.
     * 여기 키가 있는 동안에는 같은 게임으로 두 번째 알림이 나가지 않는다.
     */
    private final Map<Long, PendingNotice> pendingNotices = new ConcurrentHashMap<>();

    /** 알림을 보내 놓고 응답을 기다리는 예약 한 건. */
    private record PendingNotice(Long reservationId, String roomNumber) {
    }

    /**
     * 그 게임을 가장 먼저 예약한 방에게 반납 알림을 보낸다.
     * <p>
     * 반납이 확정되는 모든 경로(사물함 닫힘 / 퇴실 일괄 반납 / 테스트 API)와 예약 취소가 이 메서드
     * 하나만 부르면 되도록, 보낼 이유가 없는 경우를 전부 여기서 걸러낸다. 호출부는 "이 게임이 방금
     * 풀렸을 수도 있다" 만 알리면 된다.
     * <p>
     * 반납 트랜잭션 안에서 불러야 한다. 사본을 AVAILABLE 로 되돌린 것과 같은 트랜잭션이라야
     * 아래 재고 확인이 방금 돌아온 사본을 본다.
     *
     * @param boardGameId 방금 재고로 돌아왔거나, 대기열이 한 칸 줄어든 게임. null 이면 아무것도 하지 않는다.
     */
    public void notifyFirstWaiting(Long boardGameId) {
        if (boardGameId == null) {
            return;
        }

        // 이미 누군가 팝업을 보고 있으면 그 응답이나 타임아웃까지 기다린다.
        // 이 한 줄이 "첫 번째 예약자에게만" 을 보장한다 - 사본이 두 벌 돌아와도 알림은 하나씩 나간다.
        if (pendingNotices.containsKey(boardGameId)) {
            log.info("이미 응답을 기다리는 예약 팝업이 있어 알림을 보내지 않는다 - boardGameId={}", boardGameId);
            return;
        }

        // 빌릴 수 없는 게임을 빌리라고 할 수는 없다. 예약 취소 경로도 이 조건 덕분에
        // '팝업 거절' 일 때만 다음 사람에게 넘어가고, 평범한 취소일 때는 조용히 끝난다.
        if (boardGameItemMapper.countAvailable(boardGameId) <= 0) {
            return;
        }

        ReservationResponse first = reservationMapper.findFirstWaiting(boardGameId);
        if (first == null) {
            return;
        }

        // 조회와 등록 사이에 다른 스레드가 먼저 잡았으면 그쪽 알림만 유효하다.
        PendingNotice notice = new PendingNotice(first.getReservationId(), first.getRoomNumber());
        if (pendingNotices.putIfAbsent(boardGameId, notice) != null) {
            log.info("다른 경로가 먼저 알림을 보내 이번 발행은 건너뛴다 - boardGameId={}", boardGameId);
            return;
        }

        mqttPublisher.reservationReady(first.getRoomNumber(), first.getReservationId(),
                boardGameId, first.getBoardGameName(), popupTimeoutSec);
        log.info("예약 반납 알림 - room={}, reservationId={}, boardGame={}, timeoutSec={}",
                first.getRoomNumber(), first.getReservationId(), first.getBoardGameName(), popupTimeoutSec);

        scheduleTimeout(boardGameId, notice);
    }

    /**
     * 팝업에 응답이 왔다는 표시. 대여(빌린다)와 예약취소(안 빌린다) 양쪽에서 부른다.
     * <p>
     * 기다리던 방과 실제 응답한 방이 같을 때만 지운다. 팝업이 떠 있는 사이 <i>다른</i> 방이
     * 그 게임을 채 갔더라도 1등의 팝업은 살아 있어야 하고, 그 처리는 타임아웃이 판단한다.
     */
    public void resolve(Long boardGameId, String roomNumber) {
        if (boardGameId == null || roomNumber == null) {
            return;
        }
        PendingNotice notice = pendingNotices.get(boardGameId);
        if (notice == null || !roomNumber.equals(notice.roomNumber())) {
            return;
        }
        if (pendingNotices.remove(boardGameId, notice)) {
            log.info("예약 팝업 응답 도착 - room={}, reservationId={}", roomNumber, notice.reservationId());
        }
    }

    /**
     * 응답 없이 시간이 지난 팝업 정리.
     * <p>
     * 예약된 작업만 취소하지 않고 {@code remove(key, value)} 로 한 번 더 확인하는 이유는,
     * 그 사이 응답이 왔거나 같은 게임에 새 팝업이 떴을 수 있어서다. 자기가 띄운 팝업이
     * 그대로 남아 있을 때만 손댄다.
     */
    private void scheduleTimeout(Long boardGameId, PendingNotice notice) {
        delayedTaskScheduler.schedule(() -> {
            try {
                if (!pendingNotices.remove(boardGameId, notice)) {
                    return;
                }

                // 무응답 사이에 다른 방이 가져갔다면 이 방은 누를 기회가 없었던 것이다.
                // 그 상태에서 예약까지 없애면 순번만 잃으므로, 대기열에 그대로 남겨 둔다.
                if (boardGameItemMapper.countAvailable(boardGameId) <= 0) {
                    log.info("팝업 무응답이지만 그 사이 재고가 나가 예약을 유지한다 - room={}, reservationId={}",
                            notice.roomNumber(), notice.reservationId());
                    return;
                }

                // 무응답은 '안 빌린다' 와 같게 본다. 여기서 비워 주지 않으면 뒤에 선 방들은
                // 이 게임이 다음에 또 반납될 때까지 알림을 받을 수 없다.
                // status = 'waiting' 조건이 UPDATE 안에 있어, 이미 대여/취소된 예약이면 0건이다.
                int cancelled = reservationMapper.cancel(notice.reservationId());
                log.info("예약 팝업 {}초 무응답 - room={}, reservationId={}, 취소={}건",
                        popupTimeoutSec, notice.roomNumber(), notice.reservationId(), cancelled);

                notifyFirstWaiting(boardGameId);
            } catch (Exception e) {
                // 여기는 스케줄러 스레드다. 올려 봐야 삼켜지므로 남길 수 있을 때 남긴다.
                log.error("예약 팝업 타임아웃 처리 실패 - boardGameId={}, reservationId={}",
                        boardGameId, notice.reservationId(), e);
            }
        }, popupTimeoutSec, TimeUnit.SECONDS);
    }
}
