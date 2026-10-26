package com.ssafy.boardgame.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@Schema(description = "룸 상태 변경 요청")
public class RoomRequest {
    @Schema(description = "상태를 변경할 방 번호", example = "A1", maxLength = 10,
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "방 번호는 필수입니다.")
    @Size(max = 10, message = "방 번호는 10자 이하여야 합니다.")
    private String roomNumber;

    // 저장 표기는 소문자다. AdminService 가 StatusUtil 상수에 맞춰 변환하므로 API 는 대문자만 받는다.
    @Schema(description = "변경할 상태. 저장 시 소문자(empty/use)로 변환된다.",
            example = "USE", allowableValues = {"EMPTY", "USE"},
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "상태는 필수입니다.")
    @Pattern(regexp = "EMPTY|USE", message = "상태는 EMPTY, USE 중 하나여야 합니다.")
    private String status;
}
