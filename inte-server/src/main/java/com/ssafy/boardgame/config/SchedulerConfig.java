package com.ssafy.boardgame.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;

/**
 * 한 번만 늦게 실행할 작업(타임아웃 복구 등)을 위한 스케줄러.
 * <p>
 * {@code @Scheduled} 는 고정 주기용이라 "지금부터 N초 뒤 한 번" 에는 맞지 않아 따로 둔다.
 * {@code @EnableScheduling} 을 켜지 않아도 되도록 스케줄러를 직접 만든다.
 */
@Configuration
public class SchedulerConfig {

    /**
     * 등록된 작업은 MQTT 발행처럼 짧게 끝나는 것뿐이라 스레드 하나로 충분하다.
     * <p>
     * 데몬 스레드로 두어 이 스케줄러가 JVM 종료를 붙잡지 않게 한다.
     * 종료 처리는 {@code @Bean} 의 destroyMethod 추론이 {@code shutdown()} 을 잡아 준다.
     */
    @Bean
    public ScheduledExecutorService delayedTaskScheduler() {
        return Executors.newSingleThreadScheduledExecutor(runnable -> {
            Thread thread = new Thread(runnable, "delayed-task");
            thread.setDaemon(true);
            return thread;
        });
    }
}
