package com.ssafy.boardgame.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.web.multipart.MultipartFile;

import java.util.ArrayList;
import java.util.List;

/**
 * 관리자 보드게임 등록 요청. 이미지 파일이 함께 오므로 JSON 이 아니라 multipart/form-data 로 받는다.
 */
@Getter
@Setter
@NoArgsConstructor
public class BoardGameCreateRequest {

    /**
     * 요청 본문에는 없는 필드. INSERT 후 MyBatis 가 생성된 PK 를 여기에 채워 준다.
     * (ReservationResponse 를 insert 파라미터로 함께 쓰는 것과 같은 방식)
     */
    private Long boardGameId;

    @NotBlank(message = "보드게임명은 필수입니다.")
    @Size(max = 100, message = "보드게임명은 100자 이하여야 합니다.")
    private String name;

    @NotNull(message = "최소 인원은 필수입니다.")
    @Min(value = 1, message = "최소 인원은 1명 이상이어야 합니다.")
    @Max(value = 99, message = "최소 인원은 99명 이하여야 합니다.")
    private Integer minPlayers;

    @NotNull(message = "최대 인원은 필수입니다.")
    @Min(value = 1, message = "최대 인원은 1명 이상이어야 합니다.")
    @Max(value = 99, message = "최대 인원은 99명 이하여야 합니다.")
    private Integer maxPlayers;

    /** board_game.difficulty 는 VARCHAR 이므로 허용 값을 애플리케이션에서 막아 준다 */
    @NotBlank(message = "난이도는 필수입니다.")
    @Pattern(regexp = "EASY|NORMAL|HARD", message = "난이도는 EASY, NORMAL, HARD 중 하나여야 합니다.")
    private String difficulty;

    @Min(value = 1, message = "플레이 시간은 1분 이상이어야 합니다.")
    @Max(value = 1440, message = "플레이 시간은 1440분 이하여야 합니다.")
    private Integer playTime;

    private String description;

    private String howToPlay;

    /** 폼에서 categoryIds 를 반복 전송하면 바인딩된다. 비어 있으면 카테고리 없이 등록된다. */
    private List<Long> categoryIds = new ArrayList<>();

    /**
     * 대표 이미지. board_game.image_url 이 nullable 이므로 선택 항목으로 두고,
     * 첨부되지 않으면 image_url 을 null 로 저장한다.
     */
    private MultipartFile image;

    /** 파일 선택 없이 빈 파트만 전송되는 경우가 있어 isEmpty 까지 확인한다 */
    public boolean hasImage() {
        return image != null && !image.isEmpty();
    }
}
