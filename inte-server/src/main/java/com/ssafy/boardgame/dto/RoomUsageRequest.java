package com.ssafy.boardgame.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 입실/퇴실 요청. 상태는 엔드포인트가 결정하므로 RoomRequest 와 달리 status 를 받지 않는다.
 */
@Data
@NoArgsConstructor
@Schema(description = "입실/퇴실 요청. 상태는 엔드포인트가 결정하므로 status 를 받지 않는다.")
public class RoomUsageRequest {

    @Schema(description = "입실/퇴실할 방 번호", example = "A1", maxLength = 10,
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "방 번호는 필수입니다.")
    @Size(max = 10, message = "방 번호는 10자 이하여야 합니다.")
    private String roomNumber;
}
