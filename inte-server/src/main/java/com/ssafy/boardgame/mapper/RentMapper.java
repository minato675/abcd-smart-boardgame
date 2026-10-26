package com.ssafy.boardgame.mapper;

import com.ssafy.boardgame.dto.ActiveRent;
import com.ssafy.boardgame.dto.ActiveRentResponse;
import com.ssafy.boardgame.dto.CabinetOpenTarget;
import com.ssafy.boardgame.dto.RentResponse;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface RentMapper {

    /** 성공 시 파라미터 객체의 rentId/rentedAt 이 채워진다. */
    int insert(RentResponse rent);

    /**
     * 방이 아직 받아가지 않은 대여(status='rent')가 붙잡고 있는 사본 id. 없으면 null.
     * <p>
     * insert 가 덮어쓸 행이 어느 사본을 들고 있었는지 알아내는 용도다. 덮어쓰기 전에
     * 그 사본을 재고로 돌려놓지 않으면 rent 에서 참조가 끊겨 영원히 'rented' 로 남는다
     * (RentService.rent 주석 참고). insert 의 UPDATE 와 같은 조건이라 대상이 어긋나지 않는다.
     */
    Long findUnpickedItemId(@Param("roomNumber") String roomNumber);

    /** 해당 방이 해당 게임을 아직 반납하지 않고 들고 있는 건수 */
    int countActiveRent(@Param("roomNumber") String roomNumber,
                        @Param("boardGameId") Long boardGameId);

    /**
     * 해당 방이 아직 반납하지 않은 대여 전체. 없으면 빈 리스트.
     * <p>
     * countActiveRent 와 같은 조건이므로, 여기 담긴 boardGameId 는 재대여/예약이
     * ALREADY_RENTED 로 거절되는 게임과 같다 — 화면이 그 버튼을 미리 감추는 근거가 된다.
     */
    List<ActiveRentResponse> findActiveRentsByRoom(@Param("roomNumber") String roomNumber);

    /**
     * 퇴실 정리용. 해당 방의 미반납 대여를 모두 반납 처리하고 play_time_sec 을 채운다.
     * 사본을 AVAILABLE 로 되돌리는 것은 BoardGameItemMapper.releaseByRoom 이 담당하며,
     * 그쪽을 반드시 먼저 호출해야 한다.
     */
    int returnAllByRoom(@Param("roomNumber") String roomNumber);

    /**
     * 해당 방이 아직 반납하지 않은 게임 ID 목록 (중복 제거). 없으면 빈 리스트.
     * <p>
     * 퇴실 일괄 반납으로 재고에 돌아올 게임들을 미리 뽑아 두는 용도다.
     * returnAllByRoom 이 지나가면 returned_at IS NULL 조건이 사라져 더는 찾을 수 없으므로
     * 반드시 그보다 먼저 호출해야 한다.
     */
    List<Long> findActiveBoardGameIds(@Param("roomNumber") String roomNumber);

    /**
     * 카드키 태그 시 카드키에 매핑된 방 번호 찾기
     */
    String findRoomNumber(@Param("controllerId") String controllerId,
                          @Param("rfid") String rfid);

    /**
     * status가 RENT or USING인 보드게임의 사물함 번호와 그 대여 상태 찾기. 없으면 null.
     * <p>
     * 상태를 함께 돌려주는 이유는 사물함을 여는 이유(수령/반납)를 컨트롤러에 알려야 하는데,
     * 그 판단이 사물함을 고른 것과 같은 대여 한 건에서 나와야 하기 때문이다.
     */
    CabinetOpenTarget findCabinetOpenTarget(@Param("roomNumber") String roomNumber);

    /**
     * 방에서 아직 끝나지 않은 대여 한 건. 없으면 null.
     * <p>
     * USING(반납 대기) 이 RENT(픽업 대기) 보다 먼저다. findCabinetNumber 가 사물함을 고를 때 쓰는
     * 우선순위와 같은 규칙이라, 열었던 사물함과 여기서 고르는 대여가 일치한다.
     */
    ActiveRent findActiveRent(@Param("roomNumber") String roomNumber);

    /**
     * 픽업 확정. RENT -> USING.
     * <p>
     * status 조건이 UPDATE 안에 있어 멱등하다. 이미 USING 이면 0 을 리턴한다.
     */
    int markUsing(@Param("rentId") Long rentId);

    /**
     * 반납 확정. USING -> RETURNED + returned_at/play_time_sec.
     * play_time_sec 계산식은 returnAllByRoom(퇴실 일괄 반납) 과 같게 맞췄다.
     * 사본을 AVAILABLE 로 되돌리는 것은 BoardGameItemMapper.updateStatus 가 담당한다.
     */
    int markReturned(@Param("rentId") Long rentId);
}
