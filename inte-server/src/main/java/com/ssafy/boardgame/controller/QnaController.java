package com.ssafy.boardgame.controller;

import com.ssafy.boardgame.common.ErrorResponse;
import com.ssafy.boardgame.dto.QnaStartResponse;
import com.ssafy.boardgame.service.QnaService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Slf4j
@RestController
@RequestMapping("/qna")
@RequiredArgsConstructor
@Tag(name = "QnA", description = "룰 설명(QnA) 세션 제어")
public class QnaController {

    private final QnaService qnaService;

    /** 태블릿의 룰 설명 버튼 */
    @Operation(summary = "룰 설명 시작",
            description = """
                    /room/{roomNumber}/qna/start 로 QnA 시작 명령을 발행한다.
                    transactionId 는 서버가 발급해 응답으로 돌려주며,
                    이후 /room/{roomNumber}/qna/res 로 올라오는 로그를 이 값으로 한 세션에 묶는다.
                    """)
    @ApiResponse(responseCode = "200", description = "QnA 시작 명령 발행 성공")
    @ApiResponse(responseCode = "400", description = "INVALID_INPUT - 요청 값 검증 실패",
            content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    @PostMapping("/start")
    public QnaStartResponse start(String roomNumber) {
        return qnaService.start(roomNumber);
    }
}
