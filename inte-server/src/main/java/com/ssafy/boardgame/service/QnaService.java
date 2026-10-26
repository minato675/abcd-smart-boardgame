package com.ssafy.boardgame.service;

import com.ssafy.boardgame.dto.QnaLog;
import com.ssafy.boardgame.dto.QnaStartResponse;
import com.ssafy.boardgame.mapper.QnaLogMapper;
import com.ssafy.boardgame.mqtt.MqttPublisher;
import com.ssafy.boardgame.mqtt.dto.QnaRes;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
@RequiredArgsConstructor
public class QnaService {

    private final QnaLogMapper qnaLogMapper;
    private final RentService rentService;
    private final MqttPublisher mqttPublisher;
    private final ScheduledExecutorService delayedTaskScheduler;

    /** start 이후 ready 를 이만큼 기다린다. 넘기면 wake word 를 강제로 되살린다. */
    @Value("${qna.ready-timeout-sec:5}")
    private long readyTimeoutSec;

    /** ready 이후 res 를 이만큼 기다린다. 넘기면 wake word 를 강제로 되살린다. */
    @Value("${qna.response-timeout-sec:60}")
    private long responseTimeoutSec;

    /**
     * 아직 응답을 기다리는 방과 그 세션 토큰.
     * <p>
     * 토큰으로 세션을 구분해야 뒤늦게 깨어난 타임아웃이 그 사이 새로 시작된 세션의
     * wake word 를 건드리지 않는다.
     */
    private final Map<String, UUID> pendingSessions = new ConcurrentHashMap<>();

    /**
     * 태블릿의 룰 설명 버튼 -> QnA 시작 명령 발행.
     * <p>
     * transactionId 는 여기서 발급한다. 이후 /room/{roomNumber}/qna/res 로 올라오는 로그를
     * 한 세션으로 묶는 키라, 명령을 보내는 쪽이 만들어야 양쪽이 같은 값을 보게 된다.
     * <p>
     * 조회만 하므로 트랜잭션을 걸지 않았다. 나중에 QnA 세션 이력 적재가 붙으면
     * DB 작업만 별도 {@code @Transactional} 메서드로 분리하고 발행은 커밋 이후에 해야 한다
     * (롤백돼도 이미 나간 MQTT 명령은 되돌릴 수 없다 - RentService.openCabinetByCard 와 같은 규칙).
     */
    public QnaStartResponse start(String roomNumber) {
        String transactionId = UUID.randomUUID().toString();
        String boardGameName = rentService.findPlayingRent(roomNumber).getBoardGameName();

        //QnA 서버 활성화
        mqttPublisher.qnaStart(roomNumber, transactionId, boardGameName);

        // ready 가 오기 전에 마이크를 끈다. ready 가 제때 오지 않으면 아래 recovery 가 되살린다.
        mqttPublisher.wakeStopListen(roomNumber);
        scheduleWakeRecovery(roomNumber, readyTimeoutSec, "QnA 준비(ready)");

        log.info("QnA 시작 명령 - roomNumber={}, transactionId={}, boardGameName={}",
                roomNumber, transactionId, boardGameName);

        return new QnaStartResponse(transactionId, roomNumber);
    }

    /**
     * QnA 서버 준비 완료(/room/{roomNumber}/qna/ready) 처리.
     * <p>
     * 마이크는 start() 에서 이미 껐다. 여기서는 res 대기용 세션 토큰으로 갈아 끼워서
     * start() 가 걸어둔 ready 대기 recovery 를 무력화하고, res 대기 recovery 를 새로 건다.
     */
    public void ready(String roomNumber) {
        scheduleWakeRecovery(roomNumber, responseTimeoutSec, "QnA 응답(res)");
        log.info("QnA 준비 완료 - 응답 대기 시작 - roomNumber={}", roomNumber);
    }

    /**
     * QnA 응답 도착(/room/{roomNumber}/qna/res) 처리.
     * <p>
     * 질의/응답을 남기고, 답이 나왔으니 start() 에서 껐던 wake word 를 다시 켠다.
     * 이 한 쌍이 맞아야 손님이 다음 질문을 호출어로 시작할 수 있다.
     *
     * @param qnaRes 해석하지 못한 페이로드였다면 필드가 비어 있을 수 있다. 그래도 wake word 는 되살린다.
     */
    public void result(String roomNumber, QnaRes qnaRes) {
        saveLog(roomNumber, qnaRes);

        // 타임아웃이 이미 켰더라도 한 번 더 보낸다. 껐는데 안 켜지는 쪽이
        // 중복으로 켜는 쪽보다 훨씬 나쁘고, 켜는 명령은 여러 번 와도 결과가 같다.
        pendingSessions.remove(roomNumber);
        mqttPublisher.wakeStartListen(roomNumber);
        log.info("QnA 응답 도착 - wake word 수신 재개 - roomNumber={}", roomNumber);
    }

    /**
     * 질의/응답 한 건을 qna_log 에 남긴다.
     * <p>
     * 실패해도 예외를 올리지 않는다. 여기서 터지면 호출자의 wake word 재개까지 건너뛰어
     * 그 방이 마이크가 꺼진 채로 남는데, 로그 한 줄을 잃는 것보다 훨씬 나쁘다.
     * <p>
     * 트랜잭션을 걸지 않았다. 단건 INSERT 라 MyBatis 가 자체 세션에서 바로 커밋하고,
     * 그래야 뒤따르는 MQTT 발행이 커밋 이후가 된다.
     */
    private void saveLog(String roomNumber, QnaRes qnaRes) {
        // transaction_id / res 는 NOT NULL 이고, 답이 없으면 남길 내용도 없다
        if (isBlank(qnaRes.getTransactionId()) || isBlank(qnaRes.getRes())) {
            log.warn("QnA 로그를 남길 수 없는 페이로드 - roomNumber={}, transactionId={}",
                    roomNumber, qnaRes.getTransactionId());
            return;
        }

        try {
            QnaLog qnaLog = new QnaLog();
            qnaLog.setTransactionId(qnaRes.getTransactionId());
            qnaLog.setRoomNumber(roomNumber);
            qnaLog.setBoardGameId(rentService.findPlayingBoardGameId(roomNumber));
            // req 는 NOT NULL 이다. 인식이 비어도(오디오만 넘긴 경우 등) 답은 남겨야 한다.
            qnaLog.setReq(qnaRes.getReq() == null ? "" : qnaRes.getReq());
            qnaLog.setRes(qnaRes.getRes());

            qnaLogMapper.insert(qnaLog);
            log.info("QnA 로그 적재 - qnaLogId={}, roomNumber={}, transactionId={}",
                    qnaLog.getQnaLogId(), roomNumber, qnaLog.getTransactionId());
        } catch (Exception e) {
            // transaction_id 가 UUID 형식이 아니면 ::uuid 캐스팅에서 여기로 온다
            log.error("QnA 로그 적재 실패 - roomNumber={}, transactionId={}",
                    roomNumber, qnaRes.getTransactionId(), e);
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    /**
     * QnA 진행 중 다음 신호(ready 또는 res)가 끝내 오지 않는 경우를 대비한 복구 예약.
     * <p>
     * start 이후 ready 가 안 오거나, ready 이후 res 가 안 오면 그 방은 wake word 가 꺼진 채로
     * 남아 호출어로 되살릴 방법이 없다(마이크를 켜는 명령을 마이크로 트리거해야 하는 상황이 된다).
     * 신호를 못 받는 것보다 늦게라도 마이크를 되살리는 편이 낫다.
     * <p>
     * 호출할 때마다 새 토큰으로 덮어써서 이전 단계(start 또는 ready)가 걸어둔 recovery 를
     * 자연스럽게 무력화한다 - 그 타이머가 나중에 깨어나도 토큰이 바뀌어 있어 아무것도 하지 않는다.
     *
     * @param waitingFor 로그에 남길, 지금 기다리는 대상 (예: "QnA 준비(ready)", "QnA 응답(res)")
     */
    private void scheduleWakeRecovery(String roomNumber, long timeoutSec, String waitingFor) {
        UUID sessionToken = UUID.randomUUID();
        pendingSessions.put(roomNumber, sessionToken);

        delayedTaskScheduler.schedule(() -> {
            // 이 세션이 그대로 남아 있을 때만 복구한다. 그 사이 다음 신호가 왔거나
            // 새 세션이 시작됐으면 남의 상태를 건드리게 되므로 아무것도 하지 않는다.
            if (!pendingSessions.remove(roomNumber, sessionToken)) {
                return;
            }
            log.warn("{}이(가) {}초 안에 오지 않아 wake word 를 되살린다 - roomNumber={}",
                    waitingFor, timeoutSec, roomNumber);
            mqttPublisher.wakeStartListen(roomNumber);
        }, timeoutSec, TimeUnit.SECONDS);
    }

}
