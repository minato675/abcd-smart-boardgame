package com.ssafy.boardgame.config;

import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

/**
 * 요청 본문을 미리 읽어 두고 몇 번이든 다시 읽을 수 있게 하는 래퍼.
 * <p>
 * 서블릿 요청 스트림은 한 번만 읽을 수 있어서, 필터에서 body 로그를 찍으면
 * 컨트롤러가 받을 데이터가 사라진다. 그래서 바이트로 들고 있다가 매번 새 스트림으로 흘려준다.
 * <p>
 * 본문 전체를 메모리에 올리므로 {@link RequestLoggingFilter}에서 JSON/텍스트 요청에만 씌운다.
 */
public class CachedBodyHttpServletRequest extends HttpServletRequestWrapper {

    private final byte[] body;

    public CachedBodyHttpServletRequest(HttpServletRequest request) throws IOException {
        super(request);
        this.body = request.getInputStream().readAllBytes();
    }

    public byte[] getBody() {
        return body;
    }

    public String getBodyAsString() {
        return new String(body, charset());
    }

    @Override
    public ServletInputStream getInputStream() {
        ByteArrayInputStream delegate = new ByteArrayInputStream(body);
        return new ServletInputStream() {
            @Override
            public int read() {
                return delegate.read();
            }

            @Override
            public int read(byte[] b, int off, int len) {
                return delegate.read(b, off, len);
            }

            @Override
            public int available() {
                return delegate.available();
            }

            @Override
            public boolean isFinished() {
                return delegate.available() == 0;
            }

            @Override
            public boolean isReady() {
                return true;
            }

            @Override
            public void setReadListener(ReadListener readListener) {
                throw new UnsupportedOperationException("본문을 이미 다 읽어 둔 래퍼라 비동기 읽기는 지원하지 않는다");
            }
        };
    }

    @Override
    public BufferedReader getReader() {
        return new BufferedReader(new InputStreamReader(getInputStream(), charset()));
    }

    private Charset charset() {
        String encoding = getCharacterEncoding();
        return encoding != null ? Charset.forName(encoding) : StandardCharsets.UTF_8;
    }
}
