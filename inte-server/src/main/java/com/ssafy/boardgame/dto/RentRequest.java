package com.ssafy.boardgame.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@NoArgsConstructor
@Schema(description = "보드게임 대여 요청")
public class RentRequest {

    @Schema(description = "대여할 보드게임 ID", example = "1", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "보드게임 ID는 필수입니다.")
    private Long boardGameId;

    @Schema(description = "대여하는 방 번호", example = "A1", maxLength = 10,
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "방 번호는 필수입니다.")
    @Size(max = 10, message = "방 번호는 10자 이하여야 합니다.")
    private String roomNumber;
}
