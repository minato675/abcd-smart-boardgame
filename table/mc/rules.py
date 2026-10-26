"""럼미큐브 런/세트/조커 판정 로직. rummikub 본체(app/domain/rules/*.py)의 핵심 규칙을
이 프로젝트의 데이터 구조(final_label 문자열, 예: "red_5", "joker")에 맞게 이식한 것.

초기 멜드(30점) 검증은 track_id 대신, 직전 턴 보드 라벨과의 멀티셋 diff로 근사한다
(find_new_groups). 다중 프레임 재검사(recheck)는 여전히 스코프 밖이다.
"""

from collections import Counter
from dataclasses import dataclass

COLORS = {"red", "blue", "black", "orange"}
MAX_JOKERS = 2  # 게임 전체에 조커가 2개뿐이라, 한 그룹에 3개 이상 잡히면 오탐/반칙


@dataclass
class RuleCheckResult:
    valid: bool
    reason_code: str | None = None
    reason: str | None = None

    @classmethod
    def ok(cls) -> "RuleCheckResult":
        return cls(valid=True)

    @classmethod
    def fail(cls, reason_code: str, reason: str) -> "RuleCheckResult":
        return cls(valid=False, reason_code=reason_code, reason=reason)


def _parse_label(label: str) -> tuple[str | None, int | None, bool]:
    """final_label -> (color, number, is_joker)."""
    if label == "joker":
        return None, None, True
    color, number = label.split("_", 1)
    return color, int(number), False


def _find_run_start(numbers: list[int], joker_count: int, total_count: int) -> int | None:
    """일반 타일 숫자들 + 조커를 합쳐 길이가 total_count인 연속 구간을 만들 수 있는
    시작 숫자를 찾는다 (시작 숫자 후보를 순회하는 방식). 못 찾으면 None.
    이 시작 숫자를 알면 조커가 정확히 몇 번 자리를 채우는지도 알 수 있어서,
    order_run_labels()가 결과 정렬에 재사용한다."""
    if total_count < 3:
        return None
    number_set = set(numbers)
    for start in range(1, 13 - total_count + 2):
        sequence = set(range(start, start + total_count))
        if number_set.issubset(sequence):
            missing = len(sequence - number_set)
            if missing == joker_count:
                return start
    return None


def validate_run(labels: list[str]) -> RuleCheckResult:
    """같은 색, 연속된 숫자 (조커로 빈 칸 채우기 가능). 시작 숫자 후보를 순회하며
    확인하는 방식(_find_run_start)이라, 조커가 채우는 정확한 자리까지 알아낼 수 있다."""
    n = len(labels)
    if n < 3:
        return RuleCheckResult.fail("LESS_THAN_THREE_TILES", "타일 수가 3개 미만입니다.")

    parsed = [_parse_label(label) for label in labels]
    jokers = [p for p in parsed if p[2]]
    normal = [p for p in parsed if not p[2]]

    colors = {color for color, _, _ in normal}
    if len(colors) > 1:
        return RuleCheckResult.fail("COLOR_MISMATCH", "색상이 서로 다릅니다.")

    numbers = [number for _, number, _ in normal]
    if len(numbers) != len(set(numbers)):
        return RuleCheckResult.fail("DUPLICATE_NUMBER", "같은 숫자가 중복됩니다.")

    if _find_run_start(numbers, len(jokers), n) is None:
        if numbers and (min(numbers) < 1 or max(numbers) > 13):
            return RuleCheckResult.fail("INVALID_13_TO_1_SEQUENCE", "숫자 1은 13 뒤에 연결할 수 없습니다.")
        return RuleCheckResult.fail("NUMBER_GAP", "숫자가 연속되지 않습니다.")

    return RuleCheckResult.ok()


def order_run_labels(labels: list[str]) -> list[str]:
    """유효한 런이면 숫자 오름차순으로 정렬된 라벨 목록을 반환한다(조커는 자신이
    채우는 자리에 위치). 유효한 런이 아니면(색상 불일치, 시퀀스 불가 등) 입력을
    그대로 반환한다 -- 호출부에서 "원래와 같은 리스트가 나오면 재정렬 안 함"으로
    구분해서 쓸 수 있다."""
    parsed = [_parse_label(label) for label in labels]
    jokers = [p for p in parsed if p[2]]
    normal = [p for p in parsed if not p[2]]
    colors = {color for color, _, _ in normal}
    if len(colors) > 1:
        return labels

    numbers = [number for _, number, _ in normal]
    start = _find_run_start(numbers, len(jokers), len(labels))
    if start is None:
        return labels

    color = next(iter(colors), None)
    number_set = set(numbers)
    return [
        f"{color}_{n}" if n in number_set else "joker"
        for n in range(start, start + len(labels))
    ]


def validate_set(labels: list[str]) -> RuleCheckResult:
    """같은 숫자, 서로 다른 색 (3~4장)."""
    n = len(labels)
    if n < 3:
        return RuleCheckResult.fail("LESS_THAN_THREE_TILES", "타일 수가 3개 미만입니다.")
    if n > 4:
        return RuleCheckResult.fail("MORE_THAN_FOUR_TILES", "타일 수가 4개를 초과합니다.")

    parsed = [_parse_label(label) for label in labels]
    normal = [p for p in parsed if not p[2]]

    numbers = {number for _, number, _ in normal}
    if len(numbers) > 1:
        return RuleCheckResult.fail("NUMBER_MISMATCH", "숫자가 서로 다릅니다.")

    colors = [color for color, _, _ in normal]
    if len(colors) != len(set(colors)):
        return RuleCheckResult.fail("DUPLICATE_COLOR", "같은 색상이 중복됩니다.")

    return RuleCheckResult.ok()


def validate_group(labels: list[str]) -> RuleCheckResult:
    """런/세트 둘 다 시도해서 맞는 쪽을 채택 (rule_engine.validate_group과 동일한 전략).
    둘 다 실패하면 세트 판정 사유를 대표로 반환."""
    joker_count = sum(1 for label in labels if label == "joker")
    if joker_count > MAX_JOKERS:
        return RuleCheckResult.fail(
            "TOO_MANY_JOKERS", f"조커가 {MAX_JOKERS}개를 초과했습니다(오탐 가능성)."
        )

    run_result = validate_run(labels)
    if run_result.valid:
        return run_result
    set_result = validate_set(labels)
    if set_result.valid:
        return set_result
    return set_result


def _joker_values_for_run(sorted_numbers: list[int], joker_count: int) -> list[int]:
    """런에서 조커가 대신하는 숫자들. 일반 타일 사이 빈칸은 확정적으로 계산되고,
    빈칸을 다 채우고 남는 조커(런 끝을 연장하는 용도)는 정확한 숫자를 알 수 없어
    0으로 근사한다(과소평가 방향 -- 실제 점수보다 낮게만 계산됨)."""
    if not sorted_numbers:
        return [0] * joker_count  # 전부 조커면 계산 불가 -- 전부 근사
    gaps: list[int] = []
    for a, b in zip(sorted_numbers, sorted_numbers[1:]):
        gaps.extend(range(a + 1, b))
    extension_count = joker_count - len(gaps)
    return gaps + [0] * max(extension_count, 0)


def _score_group(labels: list[str]) -> int:
    """그룹 하나의 점수(조커 포함). validate_group과 동일한 순서(런 -> 세트)로
    타입을 재확인해서 조커 값을 계산한다. 이미 유효성 검증된 그룹만 넘겨야 한다."""
    parsed = [_parse_label(label) for label in labels]
    jokers = [p for p in parsed if p[2]]
    normal = [p for p in parsed if not p[2]]
    numbers = [number for _, number, _ in normal]

    if validate_run(labels).valid:
        joker_values = _joker_values_for_run(sorted(numbers), len(jokers))
        return sum(numbers) + sum(joker_values)
    if validate_set(labels).valid:
        set_number = numbers[0] if numbers else 0  # 세트는 조커도 같은 숫자 -- 확정적
        return sum(numbers) + set_number * len(jokers)
    return 0  # 무효 그룹 (호출 전에 이미 걸러졌어야 함)


def find_new_groups(current_groups: list[dict], previous_labels: list[str]) -> list[dict]:
    """직전 턴 보드 라벨과 비교해서, 모든 타일이 새로 추가된 것으로만 이루어진
    그룹을 찾는다 (기존 타일이 하나라도 섞인 그룹은 후보에서 제외 -- 재배치와
    손에서 새로 낸 것을 구분). 같은 라벨 타일이 여러 장이어도 멀티셋 개수로 처리한다."""
    current_all = Counter(label for group in current_groups for label in group["labels"])
    remaining = current_all - Counter(previous_labels)  # 이번 턴에 늘어난 만큼만 남음

    new_groups = []
    for group in current_groups:
        group_labels = Counter(group["labels"])
        if all(remaining[label] >= count for label, count in group_labels.items()):
            new_groups.append(group)
            remaining -= group_labels
    return new_groups


def calculate_meld_score(new_groups: list[dict]) -> int:
    return sum(_score_group(group["labels"]) for group in new_groups)


def validate_initial_meld(new_groups: list[dict], min_score: int = 30) -> tuple[bool, int]:
    """반환: (통과 여부, 점수). 새로 생긴 그룹이 하나도 없으면 무조건 미달."""
    if not new_groups:
        return False, 0
    score = calculate_meld_score(new_groups)
    return score >= min_score, score
