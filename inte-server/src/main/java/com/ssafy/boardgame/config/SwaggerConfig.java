package com.ssafy.boardgame.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

/**
 * Swagger UI(OpenAPI 3) 설정.
 * <p>
 * 접속 경로: 로컬 http://localhost:8111/swagger-ui.html, 배포 https://i15a402.p.ssafy.io/inte/swagger-ui.html
 */
@Configuration
public class SwaggerConfig {

    @Bean
    public OpenAPI boardgameOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("보드게임 카페 무인 관리 API")
                        .description("""
                                보드게임 대여/예약, 룸 입퇴실, 사물함 제어를 담당하는 서버 API.

                                별도의 인증은 없으며 `roomNumber` 가 방을 식별하는 값으로 쓰인다.
                                실패 응답은 공통 형식(`code`, `message`)을 따른다.
                                """)
                        .version("v1"))
                // nginx 가 /inte 접두사를 떼고 넘기므로 배포 환경에서는 서버 URL 에 접두사가 필요하다.
                .servers(List.of(
                        new Server().url("/").description("로컬 (직접 접속)"),
                        new Server().url("/inte").description("배포 (nginx 경유)")
                ));
    }

    /** 실제 서비스 API. 개발용 테스트 컨트롤러는 별도 그룹으로 분리한다. */
    @Bean
    public GroupedOpenApi serviceApi() {
        return GroupedOpenApi.builder()
                .group("1-service")
                .displayName("서비스 API")
                .pathsToMatch("/boardgame/**", "/rent/**", "/reservation/**", "/admin/**")
                .build();
    }

    /** MQTT/DB 확인용 개발 편의 API. */
    @Bean
    public GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
                .group("2-internal")
                .displayName("테스트/운영 API")
                .pathsToMatch("/api/mqtt/**", "/db/**", "/health")
                .build();
    }
}
