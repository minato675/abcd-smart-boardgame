package com.ssafy.boardgame.mqtt;

import java.util.ArrayList;
import java.util.List;

/**
 * MQTT 토픽 필터 매칭 유틸.
 * <p>
 * 브로커가 보내주는 RECEIVED_TOPIC 헤더는 "cabinet/3/status" 처럼 구체 토픽이고,
 * 핸들러가 선언하는 건 "cabinet/+/status" 같은 필터다.
 * 따라서 Map.get(topic) 으로는 절대 매칭되지 않고 아래 규칙대로 세그먼트 비교가 필요하다.
 * <ul>
 *     <li>'+' : 정확히 한 레벨에 매칭</li>
 *     <li>'#' : 남은 레벨 전체에 매칭(0개 포함). 필터의 마지막 세그먼트에만 올 수 있다.</li>
 * </ul>
 */
public class MqttTopicMatcher {

    public static final String SINGLE_LEVEL = "+";
    public static final String MULTI_LEVEL = "#";

    private static final String SEPARATOR = "/";

    /**
     * 토픽 필터가 수신 토픽에 매칭되는지 검사한다.
     */
    public static boolean matches(String filter, String topic) {
        if (filter == null || topic == null) {
            return false;
        }
        if (filter.equals(topic)) {
            return true;
        }

        String[] filterSegments = filter.split(SEPARATOR, -1);
        String[] topicSegments = topic.split(SEPARATOR, -1);

        int i = 0;
        for (; i < filterSegments.length; i++) {
            String segment = filterSegments[i];

            // '#' 는 마지막 세그먼트일 때만 유효하고, 그 뒤 레벨은 전부 매칭된다
            if (MULTI_LEVEL.equals(segment)) {
                return i == filterSegments.length - 1;
            }
            // 필터가 수신 토픽보다 깊으면 매칭 실패 ("a/+" vs "a")
            if (i >= topicSegments.length) {
                return false;
            }
            if (!SINGLE_LEVEL.equals(segment) && !segment.equals(topicSegments[i])) {
                return false;
            }
        }
        // 수신 토픽이 필터보다 깊으면 매칭 실패 ("a/+" vs "a/b/c")
        return i == topicSegments.length;
    }

    /**
     * 필터 우선순위 점수. 높을수록 구체적이다.
     * 여러 필터가 같은 토픽에 걸릴 때 구체적인 쪽을 먼저 태우기 위해 쓴다.
     * 예) cabinet/3/status(6) > cabinet/+/status(5) > cabinet/#(1)
     */
    public static int specificity(String filter) {
        int score = 0;
        for (String segment : filter.split(SEPARATOR, -1)) {
            if (MULTI_LEVEL.equals(segment)) {
                score -= 1;
            } else if (SINGLE_LEVEL.equals(segment)) {
                score += 1;
            } else {
                score += 2;
            }
        }
        return score;
    }

    /**
     * 필터의 '+' 자리에 들어있는 실제 값을 순서대로 뽑는다.
     * 예) filter="cabinet/+/status", topic="cabinet/3/status" -> ["3"]
     * <p>
     * 토픽에 식별자를 실어보내는 구조(cabinet/{cabinetId}/status)에서 핸들러가 id 를 꺼낼 때 쓴다.
     * 매칭되지 않는 조합이면 빈 리스트를 준다.
     */
    public static List<String> wildcardValues(String filter, String topic) {
        if (!matches(filter, topic)) {
            return List.of();
        }

        String[] filterSegments = filter.split(SEPARATOR, -1);
        String[] topicSegments = topic.split(SEPARATOR, -1);

        List<String> values = new ArrayList<>();
        for (int i = 0; i < filterSegments.length && i < topicSegments.length; i++) {
            if (SINGLE_LEVEL.equals(filterSegments[i])) {
                values.add(topicSegments[i]);
            }
        }
        return values;
    }
}
