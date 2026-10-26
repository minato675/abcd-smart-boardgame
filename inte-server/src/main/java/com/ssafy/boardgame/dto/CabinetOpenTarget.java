package com.ssafy.boardgame.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * 카드 태그로 열어야 할 사물함 한 건 (서비스 내부용).
 * <p>
 * 사물함 번호와 여는 이유(rentStatus)를 한 번의 조회로 함께 가져오기 위한 그릇이다.
 * 둘을 따로 조회하면 그 사이에 대여 상태가 바뀌어, 실제로 연 사물함과 컨트롤러에 알린
 * mode 가 어긋날 수 있다.
 * <p>
 * cabinetNumber 는 사본에 사물함이 지정돼 있지 않으면 null 이다.
 */
@Getter
@Setter
@NoArgsConstructor
public class CabinetOpenTarget {

    private Integer cabinetNumber;
    private String rentStatus;
}
