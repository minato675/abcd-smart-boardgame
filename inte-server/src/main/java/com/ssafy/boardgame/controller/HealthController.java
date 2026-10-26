package com.ssafy.boardgame.controller;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "운영 - 헬스체크", description = "배포 파이프라인이 기동 확인에 사용하는 엔드포인트")
public class HealthController {
    @Operation(summary = "헬스체크", description = "정상이면 문자열 `OK` 를 반환한다.")
    @GetMapping("/health")
    public String health() {
        return "OK";
    }
}
