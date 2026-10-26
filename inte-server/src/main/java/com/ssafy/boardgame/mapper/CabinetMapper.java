package com.ssafy.boardgame.mapper;

import com.ssafy.boardgame.dto.CabinetHistory;
import com.ssafy.boardgame.util.StatusUtil;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface CabinetMapper {

    /**
     * 카드 태그로 시작된 트랜잭션 기록.
     * <p>
     * 컨트롤러가 이후 올리는 개폐 보고에는 사물함 번호와 transactionId 뿐이라,
     * 어느 카드가 시작한 거래인지는 이 행에만 남는다.
     * created_at 은 DB DEFAULT 이므로 넘기지 않는다.
     */
    int insertCabinetTransaction(@Param("transactionId") String transactionId,
                                 @Param("cardUid") String cardUid,
                                 @Param("roomNumber") String roomNumber);

    /**
     * 사물함 이력 한 건 적재.
     * cabinet_log_id / created_at 은 DB 가 채우므로 넘기지 않는다.
     */
    int insertCabinetHistory(@Param("transactionId") String transactionId,
                             @Param("cabinetId") long cabinetId,
                             @Param("eventType") String eventType,
                             @Param("triggeredBy") String triggeredBy,
                             @Param("step") int step);

    /**
     * 이 거래에서 다음에 쓸 step. 이력이 아직 없으면 1.
     * <p>
     * 같은 transaction_id 의 가장 최신 이력 step + 1 로, insertCabinetHistory 의 계산식과 같다.
     * 두 곳이 같은 규칙이어야 열기 명령으로 내려보낸 step 과 그 뒤에 적재되는 OPEN 이력의
     * step 이 같은 값이 된다(컨트롤러는 상태 보고에 이 step 을 그대로 돌려준다).
     */
    CabinetHistory findCabinetHistoryByTransactionId(@Param("transactionId") String transactionId);

    /**
     * 이 거래에서 다음에 내려보낼/적재할 step.
     * findCabinetHistoryByTransactionId 조회 후의 계산 규칙을 한 곳으로 모은 것.
     */
    default int resolveNextStep(String transactionId) {
        CabinetHistory cabinetHistory = findCabinetHistoryByTransactionId(transactionId);
        if (cabinetHistory == null) {
            return 1;
        }
        if (StatusUtil.CABINET_EVENT_CLOSE.equals(cabinetHistory.getEventType())) {
            return cabinetHistory.getStep() + 1;
        }
        return cabinetHistory.getStep();
    }

    /**
     * transactionId 로 태그한 카드를 되찾는다. 짝이 없으면 null.
     * <p>
     * transaction_id 에 PK/UNIQUE 가 없어 QoS 1 재전송 시 같은 값이 여러 행일 수 있다.
     * 그대로 두면 resultType 이 단일값이라 TooManyResultsException 이 나므로 최신 한 건만 쓴다.
     */
    String findCardUid(@Param("transactionId") String transactionId);

    /**
     * 사물함의 현재 상태를 읽고 그 행을 잠근다. 없으면 null.
     * <p>
     * 존재 확인과 "직전 상태" 확인을 한 번에 한다. 직전 상태가 필요한 이유는
     * 같은 상태 보고가 두 번 와도(QoS 1) 뒤처리를 한 번만 하기 위해서다.
     * FOR UPDATE 로 잠가서 같은 사물함 메시지가 동시에 들어와도 순서대로 처리된다.
     */
    String findStatusForUpdate(@Param("cabinetId") long cabinetId);

    /**
     * 사물함 현재 상태 갱신.
     * cabinet_history 에는 FK 가 없어 이력만으로는 미등록 사물함을 걸러낼 수 없다.
     * 존재하지 않는 cabinetId 면 0 을 리턴하므로 호출부가 이 값으로 판별한다.
     */
    int updateStatus(@Param("cabinetId") long cabinetId,
                     @Param("status") String status);
}
