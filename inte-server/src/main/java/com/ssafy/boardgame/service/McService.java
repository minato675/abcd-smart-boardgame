package com.ssafy.boardgame.service;

import com.ssafy.boardgame.common.BusinessException;
import com.ssafy.boardgame.common.ErrorCode;
import com.ssafy.boardgame.dto.ActiveRentResponse;
import com.ssafy.boardgame.dto.BoardGameDetailResponse;
import com.ssafy.boardgame.dto.McSessionResponse;
import com.ssafy.boardgame.dto.McStartResponse;
import com.ssafy.boardgame.dto.McTurnLog;
import com.ssafy.boardgame.dto.McTurnLogResponse;
import com.ssafy.boardgame.dto.McTurnResponse;
import com.ssafy.boardgame.dto.McViolationLog;
import com.ssafy.boardgame.mapper.BoardGameMapper;
import com.ssafy.boardgame.mapper.McTurnLogMapper;
import com.ssafy.boardgame.mapper.McViolationLogMapper;
import com.ssafy.boardgame.mqtt.MqttPublisher;
import com.ssafy.boardgame.mqtt.dto.McTile;
import com.ssafy.boardgame.mqtt.dto.McTurnLogEvent;
import com.ssafy.boardgame.mqtt.dto.McViolationEvent;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Slf4j
@Service
@RequiredArgsConstructor
public class McService {

    /** 게임에 인원 범위가 없을 때 쓰는 상한. 좌석 회전이 깨지지 않을 정도만 막는다. */
    private static final int MAX_PLAYER_COUNT = 8;

    private final RentService rentService;
    private final BoardGameMapper boardGameMapper;
    private final McTurnLogMapper mcTurnLogMapper;
    private final McViolationLogMapper mcViolationLogMapper;
    private final MqttPublisher mqttPublisher;
    private final ObjectMapper objectMapper;

    /**
     * 진행 중인 심판 세션 한 건.
     * <p>
     * 좌석 상태가 판 도중에 바뀌므로 record 가 아니라 가변 클래스다. 바꾸는 경로는
     * analyze / finishPlayer 둘뿐이고, 둘 다 이 객체를 잠그고 들어간다 - 한 방에
     * 태블릿이 둘 붙는 일은 없지만, 회전 도중에 끼어들면 같은 좌석으로 두 번
     * 지시가 나가고 그 뒤로 화면과 진행자가 계속 어긋난다.
     */
    private static final class McSession {

        /** mc/cmd/* 에 실어 보내는 식별자 */
        private final String sessionId;
        /**
         * 진행자에게 넘긴 게임 코드. 세션 복원 응답에 그대로 쓴다 -
         * 다시 조회하면 그 사이 대여가 바뀌었을 때 화면에 다른 이름이 뜬다.
         */
        private final String boardGameName;
        /**
         * 심판을 켤 때 방이 빌리고 있던 게임. 이벤트 로그에 그대로 남긴다 -
         * 이벤트가 올라올 때마다 다시 조회하면 그 사이 반납/추가 대여가 있었을 때
         * 같은 판의 기록이 서로 다른 게임으로 갈린다.
         */
        private final Long boardGameId;
        /** 이 판을 하는 사람 수. 좌석은 1..playerCount 로 고정이다. */
        private final int playerCount;
        /**
         * 좌석별 완료 순위. 0 이면 아직 진행 중이다. 인덱스 0 이 1번 좌석.
         * <p>
         * 불리언이 아니라 순위인 이유: 손패를 다 낸 순서가 곧 등수라, 나중에 결과를
         * 보여주려면 순서가 남아야 한다. 회전에서 건너뛰는 판단에는 0 여부만 쓴다.
         */
        private final int[] finishedRank;

        /** 지금 차례. 항상 아직 안 끝난 좌석을 가리킨다. */
        private int currentSeat = 1;
        private int finishedCount = 0;

        private McSession(String sessionId, String boardGameName, Long boardGameId, int playerCount) {
            this.sessionId = sessionId;
            this.boardGameName = boardGameName;
            this.boardGameId = boardGameId;
            this.playerCount = playerCount;
            this.finishedRank = new int[playerCount];
        }

        private String sessionId() {
            return sessionId;
        }

        private String boardGameName() {
            return boardGameName;
        }

        private Long boardGameId() {
            return boardGameId;
        }

        /** 아직 손패를 다 내지 않은 인원 */
        private int remainingPlayers() {
            return playerCount - finishedCount;
        }

        /**
         * 다음 차례 좌석. 끝난 사람은 건너뛴다. 남은 사람이 없으면 0.
         * <p>
         * 자기 자신을 마지막에 검사하므로 혼자 남았으면 그대로 자기 좌석이 나온다.
         */
        private int nextSeat() {
            for (int i = 0; i < playerCount; i++) {
                int seat = (currentSeat + i) % playerCount + 1;
                if (finishedRank[seat - 1] == 0) return seat;
            }
            return 0;
        }

        /** 완료 순서대로 정렬한 좌석 목록 (화면 복원용) */
        private List<Integer> finishedSeats() {
            List<Integer> seats = new ArrayList<>(finishedCount);
            for (int rank = 1; rank <= finishedCount; rank++) {
                for (int seat = 1; seat <= playerCount; seat++) {
                    if (finishedRank[seat - 1] == rank) seats.add(seat);
                }
            }
            return seats;
        }
    }

    /** JSONB 로 저장한 테이블 상태를 다시 읽을 때 쓰는 타입 */
    private static final TypeReference<List<List<McTile>>> TABLE_TYPE = new TypeReference<>() {
    };

    /**
     * 방마다 진행 중인 심판 세션.
     * <p>
     * analyze 는 어느 판에 대한 지시인지 실어야 하는데, 태블릿이 sessionId 를 들고 있으면
     * 새로고침 한 번에 잃는다. 명령을 발행하는 쪽이 들고 있는 편이 맞다.
     * <p>
     * 메모리에만 있어서 서버를 재배포하면 사라진다 - 그러면 그 방은 심판을 다시 켜야 한다.
     * 세션 이력을 DB 에 적재하게 되면 거기서 복원할 수 있다.
     */
    private final Map<String, McSession> activeSessions = new ConcurrentHashMap<>();

    /**
     * 태블릿의 AI 심판 버튼 -> 진행자 시작 명령 발행.
     * <p>
     * sessionId 는 여기서 발급한다. 이후 /room/{roomNumber}/mc/event/turn-log 와
     * mc/event/violation 으로 올라오는 이벤트를 한 판으로 묶는 키라, 명령을 보내는 쪽이
     * 만들어야 양쪽이 같은 값을 보게 된다(QnaService.start 의 transactionId 와 같은 규칙).
     * <p>
     * 어느 게임인지는 RentService 가 판단한다 - 룰 설명과 같은 한 곳에서 골라야
     * 두 기능이 서로 다른 게임을 집는 일이 없다.
     * <p>
     * 조회만 하므로 트랜잭션을 걸지 않았다. 나중에 세션 이력 적재가 붙으면 DB 작업만
     * 별도 {@code @Transactional} 메서드로 분리하고 발행은 커밋 이후에 해야 한다
     * (롤백돼도 이미 나간 MQTT 명령은 되돌릴 수 없다).
     *
     * @param playerCount 이 판을 하는 사람 수. 태블릿이 물어봐서 보낸다 - 카메라는
     *                    테이블만 보므로 몇 명인지 셀 수 없고, 방 정원(room.capacity)이나
     *                    예약 인원은 실제로 앉은 사람 수와 다르다.
     * @throws BusinessException 대여 중인 게임이 없는 경우 (NO_ACTIVE_RENT - 심판할 대상이 없다),
     *                           게임의 인원 범위를 벗어난 경우 (INVALID_PLAYER_COUNT)
     */
    public McStartResponse start(String roomNumber, int playerCount) {
        // 이미 켜져 있으면 새 판을 시작하지 않고 그대로 돌려준다.
        // 새 sessionId 로 덮어쓰면 그때까지 쌓인 mc_turn_log 가 통째로 조회되지 않고,
        // 진행자에게는 finish 없이 start 가 한 번 더 나가 판이 둘로 갈린다.
        //
        // 인원도 마찬가지로 요청 값을 무시한다. 판 도중에 바꾸면 좌석 배열 크기가 달라져
        // 진행자가 들고 있는 좌석별 상태(첫 등록 여부)가 통째로 어긋난다.
        McSession existing = activeSessions.get(roomNumber);
        if (existing != null) {
            log.info("이미 진행 중인 AI 심판이라 그대로 돌려준다 - roomNumber={}, sessionId={}, playerCount={}",
                    roomNumber, existing.sessionId(), existing.playerCount);
            return new McStartResponse(existing.sessionId(), existing.boardGameName(), roomNumber,
                    existing.playerCount, existing.currentSeat);
        }

        String sessionId = UUID.randomUUID().toString();
        ActiveRentResponse playing = rentService.findPlayingRent(roomNumber);
        String boardGameName = playing.getBoardGameName();

        validatePlayerCount(playing.getBoardGameId(), playerCount);

        // TODO 비즈니스 로직: AI 심판 지원 게임인지 검증, 세션 이력 적재

        // 발행 전에 등록한다. 발행 직후 태블릿이 바로 턴을 넘겨도 세션을 찾을 수 있어야 한다.
        activeSessions.put(roomNumber,
                new McSession(sessionId, boardGameName, playing.getBoardGameId(), playerCount));
        mqttPublisher.mcStart(roomNumber, sessionId, boardGameName, playerCount);

        log.info("AI 심판 시작 명령 - roomNumber={}, sessionId={}, boardGameName={}, playerCount={}",
                roomNumber, sessionId, boardGameName, playerCount);

        // 첫 차례는 항상 1번이다 (McSession 초기값).
        return new McStartResponse(sessionId, boardGameName, roomNumber, playerCount, 1);
    }

    /**
     * 요청한 인원이 이 게임으로 할 수 있는 수인지.
     * <p>
     * 루미큐브 2~4 를 여기 박아 두지 않고 board_game 의 값을 읽는다 - 지원 게임이
     * 늘 때마다 코드를 고치게 되고, 화면(SUPPORTED_GAMES)에 이미 같은 문제가 있다.
     * 컬럼이 비어 있는 게임은 좌석 회전이 깨지지 않을 정도(1..8)만 막는다.
     */
    private void validatePlayerCount(Long boardGameId, int playerCount) {
        if (playerCount < 1 || playerCount > MAX_PLAYER_COUNT) {
            throw new BusinessException(ErrorCode.INVALID_PLAYER_COUNT);
        }
        if (boardGameId == null) {
            return;
        }

        BoardGameDetailResponse game = boardGameMapper.findDetailById(boardGameId);
        if (game == null) {
            return;
        }

        Integer min = game.getMinPlayers();
        Integer max = game.getMaxPlayers();
        if ((min != null && playerCount < min) || (max != null && playerCount > max)) {
            log.warn("게임 인원 범위를 벗어난 요청 - boardGameId={}, playerCount={}, 범위={}~{}",
                    boardGameId, playerCount, min, max);
            throw new BusinessException(ErrorCode.INVALID_PLAYER_COUNT);
        }
    }

    /**
     * 턴 넘기기 -> 진행자 분석 지시 발행.
     * <p>
     * 손님이 수를 두고 나면 테이블을 다시 읽어야 하므로, 그 시점을 태블릿이 알려 준다.
     * 결과는 /room/{roomNumber}/mc/event/turn-log 로 올라온다.
     * <p>
     * 지시에는 방금 차례를 마친 좌석을 싣는다. 카메라는 누가 뒀는지 모르는데, 루미큐브의
     * 첫 등록 30점처럼 "이 사람이 이미 등록했는가" 로 갈리는 규칙을 판정하려면 필요하다.
     * <p>
     * 좌석은 발행 결과를 기다리지 않고 바로 넘긴다. turn-log 를 받고 넘기면 진행자가
     * 죽거나 응답이 유실됐을 때 그 방의 차례가 영영 멈춘다 - 어차피 "이 사람 수가 끝났다"
     * 를 아는 근거는 진행자의 판정이 아니라 손님이 누른 이 버튼이다.
     *
     * @return 방금 마친 좌석과 다음 차례
     * @throws BusinessException 진행 중인 세션이 없는 경우 (MC_SESSION_NOT_FOUND)
     */
    public McTurnResponse analyze(String roomNumber) {
        McSession session = requireSession(roomNumber);

        int playerId;
        int nextSeat;
        int remaining;
        synchronized (session) {
            requireLive(session);
            playerId = session.currentSeat;
            nextSeat = session.nextSeat();
            session.currentSeat = nextSeat;
            remaining = session.remainingPlayers();
        }

        mqttPublisher.mcAnalyze(roomNumber, session.sessionId(), playerId);
        log.info("AI 심판 분석 지시 - roomNumber={}, sessionId={}, playerId={}, 다음좌석={}",
                roomNumber, session.sessionId(), playerId, nextSeat);

        //wake word 서버에서 단어를 인식하면 stop listen을 자체적으로 해버려서 다시 켜기
        mqttPublisher.wakeStartListen(roomNumber);

        return new McTurnResponse(playerId, nextSeat, remaining, false);
    }

    /**
     * '다 냈어요' - 지금 차례인 사람이 손패를 비웠다.
     * <p>
     * 카메라는 테이블만 보고 손패는 못 보므로, 누가 끝났는지는 사람이 알려주는 수밖에 없다.
     * <p>
     * 진행자에게는 아무것도 보내지 않는다. 끝난 좌석으로 analyze 를 더 보내지 않는 것만으로
     * 충분하고, 진행자가 알아야 할 이유가 없다(좌석별 상태를 쓰는 쪽은 진행자지만 그건
     * "지시가 온 좌석" 에 대해서만 필요하다).
     * <p>
     * 남은 사람이 하나뿐이면 세션까지 끝낸다. 혼자 두는 턴은 판정할 대상이 아니고,
     * 그대로 두면 손님이 심판을 따로 꺼야 한다.
     *
     * @return 끝난 좌석과 다음 차례. sessionEnded 가 true 면 세션은 이미 정리됐다.
     * @throws BusinessException 진행 중인 세션이 없는 경우 (MC_SESSION_NOT_FOUND)
     */
    public McTurnResponse finishPlayer(String roomNumber) {
        McSession session = requireSession(roomNumber);

        int seat;
        int nextSeat;
        int remaining;
        synchronized (session) {
            requireLive(session);
            seat = session.currentSeat;
            session.finishedRank[seat - 1] = ++session.finishedCount;
            remaining = session.remainingPlayers();

            if (remaining <= 1) {
                // 마지막 한 명에게도 등수를 준다 - 끝까지 남은 것도 결과의 일부다.
                nextSeat = 0;
                for (int s = 1; s <= session.playerCount; s++) {
                    if (session.finishedRank[s - 1] == 0) {
                        session.finishedRank[s - 1] = ++session.finishedCount;
                    }
                }
                session.currentSeat = 0;
            } else {
                nextSeat = session.nextSeat();
                session.currentSeat = nextSeat;
            }
        }

        if (remaining > 1) {
            log.info("좌석 완료 - roomNumber={}, sessionId={}, seat={}, 남은인원={}, 다음좌석={}",
                    roomNumber, session.sessionId(), seat, remaining, nextSeat);
            return new McTurnResponse(seat, nextSeat, remaining, false);
        }

        // 세션 정리는 finish 와 같은 경로를 탄다 - 진행자에게 mc/cmd/finish 가 나가야
        // 저쪽도 좌석 상태를 버린다. remove 먼저 해서 뒤늦은 요청이 끼어들지 못하게 한다.
        activeSessions.remove(roomNumber, session);
        mqttPublisher.mcFinish(roomNumber, session.sessionId());
        log.info("마지막 한 명만 남아 AI 심판을 종료한다 - roomNumber={}, sessionId={}, seat={}",
                roomNumber, session.sessionId(), seat);

        return new McTurnResponse(seat, 0, remaining, true);
    }

    private McSession requireSession(String roomNumber) {
        McSession session = activeSessions.get(roomNumber);
        if (session == null) {
            throw new BusinessException(ErrorCode.MC_SESSION_NOT_FOUND);
        }
        return session;
    }

    /**
     * 이미 끝난 세션을 잡고 있는지 확인한다.
     * <p>
     * 맵에서 빼기 직전에 다른 요청이 같은 객체를 집어 갈 수 있다. currentSeat 이 0 이면
     * 마지막 한 명까지 끝나 정리된 세션이라, 그대로 두면 finishedRank[-1] 로 터진다.
     * 호출자 입장에서는 세션이 없는 것과 같은 상황이므로 같은 코드로 돌려준다.
     */
    private static void requireLive(McSession session) {
        if (session.currentSeat == 0) {
            throw new BusinessException(ErrorCode.MC_SESSION_NOT_FOUND);
        }
    }

    /**
     * 심판 끄기 -> 진행자 정상 종료 지시 발행.
     * <p>
     * analyze 와 달리 세션이 없어도 예외를 던지지 않는다. 끄는 요청은 "꺼진 상태로 만들어라"
     * 라는 뜻이라 이미 꺼져 있으면 그것으로 목적이 달성된 것이고, 여기서 막으면 서버를
     * 재배포해 세션을 잃은 방이 화면의 심판 패널을 영영 닫지 못한다.
     */
    public void finish(String roomNumber) {
        McSession session = activeSessions.remove(roomNumber);
        if (session == null) {
            log.warn("종료할 AI 심판 세션이 없다 - roomNumber={}", roomNumber);
            return;
        }

        mqttPublisher.mcFinish(roomNumber, session.sessionId());
        log.info("AI 심판 종료 지시 - roomNumber={}, sessionId={}", roomNumber, session.sessionId());
    }

    /**
     * 진행자가 읽은 테이블 상태(/room/{roomNumber}/mc/event/turn-log) 적재.
     * <p>
     * 세트/타일 순서가 의미를 갖는 스냅샷이고 항상 한 턴 통째로만 읽히므로,
     * 타일을 행으로 펴지 않고 JSONB 한 컬럼에 담는다(db/mc_turn_log.sql 참고).
     * turn_no 는 페이로드에 없어 매퍼가 같은 세션의 기존 행에서 이어 매긴다.
     */
    public void recordTurnLog(String roomNumber, McTurnLogEvent event) {
        if (event.getSessionId() == null || event.getSessionId().isBlank()
                || event.getTable() == null) {
            log.warn("테이블 상태를 남길 수 없는 페이로드 - roomNumber={}, sessionId={}",
                    roomNumber, event.getSessionId());
            return;
        }

        try {
            McTurnLog turnLog = new McTurnLog();
            turnLog.setSessionId(event.getSessionId());
            turnLog.setRoomNumber(roomNumber);
            turnLog.setTileCount(countTiles(event.getTable()));
            // 받은 그대로가 아니라 파싱한 결과를 다시 직렬화한다 - 규격 밖 필드가 섞여
            // 들어오거나 number 가 문자열로 와도 저장되는 형태는 항상 같다.
            turnLog.setTableState(objectMapper.writeValueAsString(event.getTable()));

            mcTurnLogMapper.insert(turnLog);
            log.info("테이블 상태 적재 - roomNumber={}, sessionId={}, turnNo={}, tileCount={}",
                    roomNumber, turnLog.getSessionId(), turnLog.getTurnNo(), turnLog.getTileCount());
        } catch (Exception e) {
            // sessionId 가 UUID 형식이 아니면 ::uuid 캐스팅에서 여기로 온다
            log.error("테이블 상태 적재 실패 - roomNumber={}, sessionId={}",
                    roomNumber, event.getSessionId(), e);
        }
    }

    /**
     * 진행 중인 세션. 없으면 null.
     * <p>
     * 태블릿이 새로고침된 뒤 화면을 복원하는 데 쓴다. 이게 없으면 태블릿은 심판이 도는지 알 수 없어
     * 권유 팝업을 다시 띄우고, 손님이 확인하면 판이 둘로 갈린다.
     * <p>
     * turnNo 까지 함께 내려준다 - 태블릿이 세는 값은 브로커로 받은 개수라 새로고침하면 0 이 되는데,
     * 화면에는 실제로 몇 턴째인지가 나와야 한다.
     */
    public McSessionResponse findActiveSession(String roomNumber) {
        McSession session = activeSessions.get(roomNumber);
        if (session == null) {
            return null;
        }

        McTurnLog latest = mcTurnLogMapper.findLatestBySession(session.sessionId());
        int turnNo = (latest == null || latest.getTurnNo() == null) ? 0 : latest.getTurnNo();

        synchronized (session) {
            return new McSessionResponse(session.sessionId(), session.boardGameName(), turnNo,
                    session.playerCount, session.currentSeat, session.finishedSeats());
        }
    }

    /**
     * '이전 화면 보기' - 진행 중인 세션의 마지막 테이블 상태.
     * <p>
     * 태블릿이 MQTT 로 받아 들고 있는 목록이 아니라 DB 를 읽는다. 새로고침하거나
     * 판 도중에 태블릿이 껐다 켜져도 마지막 화면을 복원할 수 있어야 한다.
     *
     * @return 아직 기록된 턴이 없으면 null
     * @throws BusinessException 진행 중인 세션이 없는 경우 (MC_SESSION_NOT_FOUND)
     */
    public McTurnLogResponse findLatestTurnLog(String roomNumber) {
        McSession session = activeSessions.get(roomNumber);
        if (session == null) {
            throw new BusinessException(ErrorCode.MC_SESSION_NOT_FOUND);
        }

        McTurnLog latest = mcTurnLogMapper.findLatestBySession(session.sessionId());
        if (latest == null) {
            log.info("아직 기록된 턴이 없다 - roomNumber={}, sessionId={}", roomNumber, session.sessionId());
            return null;
        }

        List<List<McTile>> table;
        try {
            table = objectMapper.readValue(latest.getTableState(), TABLE_TYPE);
        } catch (Exception e) {
            // 저장할 때 파싱한 결과를 다시 직렬화하므로 여기서 깨질 일은 없지만,
            // 손으로 넣은 행이 섞여 있으면 화면 전체가 에러가 되는 것보다 빈 테이블이 낫다.
            log.error("저장된 테이블 상태를 해석할 수 없다 - turnLogId={}", latest.getTurnLogId(), e);
            table = List.of();
        }

        return new McTurnLogResponse(latest.getTurnNo(), latest.getTileCount(), table);
    }

    /**
     * 규칙 위반(/room/{roomNumber}/mc/event/violation) 적재.
     * <p>
     * 손님에게 알리는 것은 태블릿이 같은 토픽을 직접 구독해서 한다 - 서버는 기록만 한다.
     * code 가 고정값이라 "어떤 규칙에서 손님들이 자주 막히는지" 를 세는 축이 된다.
     */
    public void recordViolation(String roomNumber, McViolationEvent event) {
        if (isBlank(event.getSessionId()) || isBlank(event.getCode())) {
            log.warn("위반을 남길 수 없는 페이로드 - roomNumber={}, sessionId={}, code={}",
                    roomNumber, event.getSessionId(), event.getCode());
            return;
        }

        try {
            McViolationLog violationLog = new McViolationLog();
            violationLog.setSessionId(event.getSessionId());
            violationLog.setRoomNumber(roomNumber);
            violationLog.setBoardGameId(resolveBoardGameId(roomNumber, event.getSessionId()));
            violationLog.setCode(event.getCode());
            violationLog.setTable(objectMapper.writeValueAsString(event.getTable()));
            // message 는 NOT NULL 이다. 문구가 비어도 어떤 위반이었는지는 남아야 한다.
            violationLog.setMessage(event.getMessage() == null ? "" : event.getMessage());

            mcViolationLogMapper.insert(violationLog);
            log.info("규칙 위반 적재 - roomNumber={}, sessionId={}, code={}",
                    roomNumber, violationLog.getSessionId(), violationLog.getCode());
        } catch (Exception e) {
            // sessionId 가 UUID 형식이 아니면 ::uuid 캐스팅에서 여기로 온다
            log.error("규칙 위반 적재 실패 - roomNumber={}, sessionId={}, code={}",
                    roomNumber, event.getSessionId(), event.getCode(), e);
        }
    }

    /**
     * 이벤트를 남길 때 붙일 보드게임 ID.
     * <p>
     * 진행 중인 세션의 값을 먼저 쓴다 - 심판을 켠 시점에 방이 빌리고 있던 게임이라,
     * 판이 진행되는 동안 다른 게임을 추가로 빌려도 같은 판의 기록이 갈리지 않는다.
     * <p>
     * 세션을 못 찾으면(서버 재배포로 잃었거나 지난 판의 뒤늦은 이벤트) 지금 방이 빌린 게임을
     * 대신 찾는다. 판이 도는 중에는 그 게임을 펼쳐 놓고 있으므로 대개 맞고, 아무것도 없으면
     * null 이다 - 통계용이라 비어도 로그 자체는 남아야 한다.
     */
    private Long resolveBoardGameId(String roomNumber, String sessionId) {
        McSession session = activeSessions.get(roomNumber);
        if (session != null && session.sessionId().equals(sessionId)) {
            return session.boardGameId();
        }

        log.warn("진행 중이 아닌 세션의 이벤트 - roomNumber={}, 수신={}, 진행중={}",
                roomNumber, sessionId, session == null ? null : session.sessionId());
        return rentService.findPlayingBoardGameId(roomNumber);
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    /** 세트 안 타일을 모두 센다. null 세트는 건너뛴다(진행자가 빈 값을 실어 보낼 수 있다). */
    private static int countTiles(List<List<McTile>> table) {
        int count = 0;
        for (List<McTile> tileSet : table) {
            if (tileSet != null) count += tileSet.size();
        }
        return count;
    }
}
