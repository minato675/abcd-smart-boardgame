package com.ssafy.boardgame.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.slf4j.MDC;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingResponseWrapper;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * 컨트롤러로 들어오는 요청/응답을 기록하는 필터.
 * <p>
 * 디버깅을 위해 URL, Parameter, Request Body, Response Status/Time, Response Body를 통합 출력한다.
 * 단, 로그 용량 폭발을 방지하기 위해 GET 등 단순 조회 메서드는 Response Body 출력을 제외한다.
 */
@Slf4j
@Component
@Order(RequestLoggingFilter.FILTER_ORDER)
@ConditionalOnProperty(name = "boardgame.request-log.enabled", matchIfMissing = true)
public class RequestLoggingFilter extends OncePerRequestFilter {

    static final int FILTER_ORDER = -9_800;

    /** 로그 용량 조절을 위한 최대 문자열 길이 */
    private static final int MAX_BODY_LENGTH = 2_000;

    /** 헬스체크·Swagger 정적 리소스 등 로그 생략 대상 */
    private static final List<String> SKIP_PREFIXES = List.of(
            "/health", "/actuator", "/favicon.ico",
            "/swagger-ui", "/v3/api-docs", "/webjars");

    /** 마스킹 필요한 민감 정보 패턴 */
    private static final Pattern SENSITIVE_NAME = Pattern.compile(
            "password|passwd|pwd|token|secret|apiKey", Pattern.CASE_INSENSITIVE);

    private static final Pattern SENSITIVE_FIELD = Pattern.compile(
            "(\"[^\"]*(?:password|passwd|pwd|token|secret|apiKey)[^\"]*\"\\s*:\\s*)\"[^\"]*\"",
            Pattern.CASE_INSENSITIVE);

    private static final String MASK = "***";
    private static final String REQUEST_ID = "requestId";

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String uri = request.getRequestURI();
        return SKIP_PREFIXES.stream().anyMatch(uri::startsWith);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {

        // 1. Request, Response 래핑
        HttpServletRequest requestToUse = shouldCacheBody(request) ? new CachedBodyHttpServletRequest(request) : request;
        ContentCachingResponseWrapper responseToUse = new ContentCachingResponseWrapper(response);

        MDC.put(REQUEST_ID, UUID.randomUUID().toString().substring(0, 8));
        long startedAt = System.nanoTime();

        try {
            chain.doFilter(requestToUse, responseToUse);
        } finally {
            long tookMs = (System.nanoTime() - startedAt) / 1_000_000;

            // 2. 통합 로그 출력
            logUnified(requestToUse, responseToUse, tookMs);

            // ★ 필수: 래퍼 버퍼의 응답 데이터를 실제 클라이언트에 전송
            responseToUse.copyBodyToResponse();
            MDC.remove(REQUEST_ID);
        }
    }

    private void logUnified(HttpServletRequest request, ContentCachingResponseWrapper response, long tookMs) {
        String query = request.getQueryString();
        String fullUrl = request.getRequestURI() + (StringUtils.hasText(query) ? "?" + query : "");
        String params = params(request);
        String reqBody = payload(request);

        // 1번 정책 반영: GET, HEAD, OPTIONS 요청은 Response Body 로그 제외
        String resBody = isResponseBodyLoggingExcluded(request.getMethod())
                ? "<EXCLUDED_FOR_" + request.getMethod() + ">"
                : responsePayload(response);

        log.info("""
                
                [HTTP REQUEST/RESPONSE LOG]
                - URL       : {} {} ({})
                - Params    : {}
                - Req Body  : {}
                - Status    : {} ({}ms)
                - Res Body  : {}
                """,
                request.getMethod(),
                fullUrl,
                clientIp(request),
                StringUtils.hasText(params) ? params : "N/A",
                StringUtils.hasText(reqBody) ? reqBody : "N/A",
                response.getStatus(),
                tookMs,
                StringUtils.hasText(resBody) ? resBody : "N/A"
        );
    }

    /**
     * GET, HEAD, OPTIONS 요청은 Response Body 로그에서 제외 처리
     */
    private boolean isResponseBodyLoggingExcluded(String method) {
        return HttpMethod.GET.matches(method)
                || HttpMethod.HEAD.matches(method)
                || HttpMethod.OPTIONS.matches(method);
    }

    /**
     * 응답 본문 추출 및 가공
     */
    private String responsePayload(ContentCachingResponseWrapper response) {
        byte[] buf = response.getContentAsByteArray();
        if (buf.length == 0) {
            return "";
        }
        String body = new String(buf, StandardCharsets.UTF_8);
        if (!isPrintable(body)) {
            return "<" + response.getContentType() + ", " + buf.length + " bytes>";
        }
        return truncate(mask(collapse(body)));
    }

    private String params(HttpServletRequest request) {
        if (isMultipart(request.getContentType())) {
            return "";
        }
        return truncate(formatParameters(request.getParameterMap()));
    }

    private String payload(HttpServletRequest request) {
        if (isMultipart(request.getContentType())) {
            return "<multipart/form-data, " + request.getContentLength() + " bytes>";
        }
        if (!(request instanceof CachedBodyHttpServletRequest cached)) {
            return "";
        }
        String body = cached.getBodyAsString();
        if (!isPrintable(body)) {
            return "<" + request.getContentType() + ", " + cached.getBody().length + " bytes>";
        }
        return truncate(mask(collapse(body)));
    }

    private String formatParameters(Map<String, String[]> parameters) {
        return parameters.entrySet().stream()
                .map(entry -> entry.getKey() + "=" + maskIfSensitive(entry.getKey(), String.join(",", entry.getValue())))
                .collect(Collectors.joining("&"));
    }

    private String clientIp(HttpServletRequest request) {
        String forwarded = request.getHeader("X-Forwarded-For");
        if (StringUtils.hasText(forwarded)) {
            return forwarded.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }

    private boolean shouldCacheBody(HttpServletRequest request) {
        String contentType = request.getContentType();
        if (isMultipart(contentType) || isFormUrlEncoded(contentType)) {
            return false;
        }
        return request.getContentLength() > 0
                || "chunked".equalsIgnoreCase(request.getHeader("Transfer-Encoding"));
    }

    private boolean isPrintable(String body) {
        return body.chars().noneMatch(c ->
                c == '�' || (c < 0x20 && c != '\n' && c != '\r' && c != '\t'));
    }

    private boolean isMultipart(String contentType) {
        return contentType != null && matches(contentType, type -> "multipart".equals(type.getType()));
    }

    private boolean isFormUrlEncoded(String contentType) {
        return contentType != null
                && matches(contentType, MediaType.APPLICATION_FORM_URLENCODED::isCompatibleWith);
    }

    private boolean matches(String contentType, Function<MediaType, Boolean> predicate) {
        try {
            return predicate.apply(MediaType.parseMediaType(contentType));
        } catch (org.springframework.http.InvalidMediaTypeException e) {
            return false;
        }
    }

    private String mask(String payload) {
        return SENSITIVE_FIELD.matcher(payload).replaceAll("$1\"" + MASK + "\"");
    }

    private String maskIfSensitive(String name, String value) {
        return SENSITIVE_NAME.matcher(name).find() ? MASK : value;
    }

    private String collapse(String payload) {
        return payload.replaceAll("\\s*\\R\\s*", "").trim();
    }

    private String truncate(String payload) {
        if (payload.length() <= MAX_BODY_LENGTH) {
            return payload;
        }
        return payload.substring(0, MAX_BODY_LENGTH) + "...(" + payload.length() + " chars)";
    }
}