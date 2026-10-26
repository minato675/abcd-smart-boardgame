package com.ssafy.boardgame.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * 인증이 없으므로 방 번호가 예약 소유 증명 역할을 한다.
 */
@Getter
@Setter
@NoArgsConstructor
@Schema(description = "예약 취소 요청. 인증이 없으므로 방 번호가 예약 소유 증명 역할을 한다.")
public class ReservationCancelRequest {

    @Schema(description = "예약을 등록한 방 번호. 예약의 방과 다르면 403 이 반환된다.",
            example = "A1", maxLength = 10, requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "방 번호는 필수입니다.")
    @Size(max = 10, message = "방 번호는 10자 이하여야 합니다.")
    private String roomNumber;

    @Schema(description = "취소할 예약 ID. `GET /reservation` 으로 조회할 수 있다.",
            example = "10", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "예약 ID는 필수입니다.")
    private Long reservationId;
}
