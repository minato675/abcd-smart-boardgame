package com.ssafy.boardgame.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@NoArgsConstructor
@Schema(description = "룰 설명(QnA) 시작 요청")
public class QnaStartRequest {

    @Schema(description = "룰 설명을 시작하는 방 번호", example = "A1", maxLength = 10,
            requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "방 번호는 필수입니다.")
    @Size(max = 10, message = "방 번호는 10자 이하여야 합니다.")
    private String roomNumber;

    @Schema(description = "룰 설명을 받을 보드게임명", example = "루미큐브",
            requiredMode = Schema.RequiredMode.REQUIRED)
    private String boardGameName;
}
