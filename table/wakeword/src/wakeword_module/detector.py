"""Pure raw-score wake-word decision policy."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from numbers import Real
from typing import Any, Callable, Mapping

from .contracts import MODEL_IDS, RawScores, WakeWordCandidate


class ScoreValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DetectorPolicy:
    id: str
    wire_status: str
    trigger_threshold: float
    evidence_window_frames: int
    required_hits: int
    vad_mode: str = "off"
    vad_threshold: float | None = None
    vad_context_oldest_lag_frames: int | None = None
    vad_context_newest_lag_frames: int | None = None
    vad_aggregate: str | None = None


def _policy_value(policy: Any, name: str, default: Any = None) -> Any:
    return getattr(policy, name, default)


class DetectionStateMachine:
    """K-of-N evidence, optional VAD context, and normalized collision arbitration.

    It has no MQTT, audio, or lifecycle side effects.  The coordinator owns the
    returned candidate and decides whether to make it durable.
    """

    def __init__(
        self,
        policies: Mapping[str, Any],
        *,
        arbitration_frames: int = 1,
        collision_margin: float | None = None,
        ambiguous_suppression_frames: int = 0,
        max_vad_history_frames: int = 64,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if set(policies) != set(MODEL_IDS):
            raise ValueError("detector requires exactly the two configured model IDs")
        if arbitration_frames < 1:
            raise ValueError("arbitration_frames must be >= 1")
        if collision_margin is not None and not 0 <= collision_margin <= 1:
            raise ValueError("collision_margin must be null or between 0 and 1")
        if ambiguous_suppression_frames < 0 or max_vad_history_frames < 1:
            raise ValueError("suppression/history values are out of range")
        self.policies = dict(policies)
        self.arbitration_frames = arbitration_frames
        self.collision_margin = collision_margin
        self.ambiguous_suppression_frames = ambiguous_suppression_frames
        self.max_vad_history_frames = max_vad_history_frames
        self.wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        for model_id, policy in self.policies.items():
            window = _policy_value(policy, "evidence_window_frames")
            hits = _policy_value(policy, "required_hits")
            threshold = _policy_value(policy, "trigger_threshold")
            if not isinstance(window, int) or window < 1 or not isinstance(hits, int) or not 1 <= hits <= window:
                raise ValueError(f"invalid evidence policy for {model_id}")
            if not isinstance(threshold, (int, float)) or not 0 < float(threshold) < 1:
                raise ValueError(f"invalid threshold for {model_id}")
            mode = _policy_value(policy, "vad_mode", "off")
            if mode == "gate":
                oldest = _policy_value(policy, "vad_context_oldest_lag_frames")
                newest = _policy_value(policy, "vad_context_newest_lag_frames")
                aggregate = _policy_value(policy, "vad_aggregate")
                vad_threshold = _policy_value(policy, "vad_threshold")
                if oldest is None or newest is None or newest > oldest or oldest >= max_vad_history_frames:
                    raise ValueError(f"invalid VAD context for {model_id}")
                if aggregate not in {"max", "mean"} or vad_threshold is None or not 0 <= vad_threshold <= 1:
                    raise ValueError(f"invalid gated VAD policy for {model_id}")
            elif mode not in {"off", "observe"}:
                raise ValueError(f"invalid VAD mode for {model_id}")
        self.reset(0)

    def reset(self, generation: int) -> None:
        self.generation = generation
        self._histories = {
            model_id: deque(maxlen=int(_policy_value(policy, "evidence_window_frames")))
            for model_id, policy in self.policies.items()
        }
        self._vad_history: deque[tuple[int, float]] = deque(maxlen=self.max_vad_history_frames)
        self._arbitration_remaining = 0
        self._arbitration_candidates: dict[str, WakeWordCandidate] = {}
        self._suppression_remaining = 0
        self._last_sequence: int | None = None
        self.fired = False

    @property
    def suppression_remaining(self) -> int:
        return self._suppression_remaining

    @property
    def histories(self) -> Mapping[str, tuple[float, ...]]:
        return {key: tuple(value) for key, value in self._histories.items()}

    def _validate_scores(self, raw: RawScores) -> dict[str, float]:
        if raw.generation != self.generation:
            return {}
        scores: dict[str, float] = {}
        for model_id in MODEL_IDS:
            if model_id not in raw.scores:
                raise ScoreValidationError(f"missing score for {model_id}")
            value = raw.scores[model_id]
            if isinstance(value, (bool,)) or not isinstance(value, Real):
                raise ScoreValidationError(f"non-numeric score for {model_id}")
            score = float(value)
            if not math.isfinite(score) or score < -1e-6 or score > 1 + 1e-6:
                raise ScoreValidationError(f"out-of-range score for {model_id}")
            scores[model_id] = min(1.0, max(0.0, score))
        if raw.vad_score is not None:
            vad = float(raw.vad_score)
            if not math.isfinite(vad) or vad < -1e-6 or vad > 1 + 1e-6:
                raise ScoreValidationError("out-of-range VAD score")
        return scores

    def _vad_allows(self, policy: Any, sequence: int) -> bool:
        if _policy_value(policy, "vad_mode", "off") != "gate":
            return True
        oldest = int(_policy_value(policy, "vad_context_oldest_lag_frames"))
        newest = int(_policy_value(policy, "vad_context_newest_lag_frames"))
        by_sequence = dict(self._vad_history)
        values: list[float] = []
        for lag in range(newest, oldest + 1):
            value = by_sequence.get(sequence - lag)
            if value is None:
                return False
            values.append(value)
        aggregate = _policy_value(policy, "vad_aggregate")
        actual = max(values) if aggregate == "max" else sum(values) / len(values)
        return actual >= float(_policy_value(policy, "vad_threshold"))

    def _candidate_for(self, model_id: str, raw: RawScores, score: float) -> WakeWordCandidate:
        policy = self.policies[model_id]
        occurred = raw.occurred_at_utc or self.wall_clock()
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        return WakeWordCandidate(
            generation=raw.generation,
            model_id=model_id,  # type: ignore[arg-type]
            wire_status=_policy_value(policy, "wire_status"),  # type: ignore[arg-type]
            raw_score=score,
            threshold=float(_policy_value(policy, "trigger_threshold")),
            frame_end_sample_index=raw.frame_end_sample_index,
            frame_end_monotonic_ns=raw.frame_end_monotonic_ns,
            occurred_at_utc=occurred.astimezone(timezone.utc),
            timestamp_uncertainty_ms=float(raw.timestamp_uncertainty_ms),
        )

    def _finish_arbitration(self) -> WakeWordCandidate | None:
        candidates = self._arbitration_candidates
        self._arbitration_candidates = {}
        self._arbitration_remaining = 0
        if not candidates:
            return None
        if len(candidates) == 1:
            self.fired = True
            return next(iter(candidates.values()))
        margins: dict[str, float] = {}
        for model_id, candidate in candidates.items():
            margin = (candidate.raw_score - candidate.threshold) / (1.0 - candidate.threshold)
            margins[model_id] = margin
        difference = abs(margins[MODEL_IDS[0]] - margins[MODEL_IDS[1]])
        if self.collision_margin is not None and difference >= self.collision_margin:
            selected_id = max(margins, key=margins.get)
            self.fired = True
            return candidates[selected_id]
        self._clear_evidence()
        self._suppression_remaining = self.ambiguous_suppression_frames
        return None

    def _clear_evidence(self) -> None:
        for history in self._histories.values():
            history.clear()
        self._vad_history.clear()

    def feed(
        self,
        raw: RawScores,
        *,
        listening: bool = True,
        engine_warming: bool = False,
    ) -> WakeWordCandidate | None:
        """Consume one frame and return at most one candidate for this generation."""

        if raw.generation != self.generation or self.fired or not listening or engine_warming:
            return None
        if self._last_sequence is not None and raw.sequence <= self._last_sequence:
            return None
        self._last_sequence = raw.sequence
        scores = self._validate_scores(raw)
        if raw.vad_score is not None:
            self._vad_history.append((raw.sequence, min(1.0, max(0.0, float(raw.vad_score)))))
        if self._suppression_remaining:
            self._suppression_remaining -= 1
            return None

        current: dict[str, WakeWordCandidate] = {}
        for model_id, score in scores.items():
            policy = self.policies[model_id]
            history = self._histories[model_id]
            history.append(score)
            threshold = float(_policy_value(policy, "trigger_threshold"))
            if sum(value >= threshold for value in history) >= int(_policy_value(policy, "required_hits")) and self._vad_allows(policy, raw.sequence):
                current[model_id] = self._candidate_for(model_id, raw, score)

        for model_id, candidate in current.items():
            previous = self._arbitration_candidates.get(model_id)
            if previous is None or candidate.raw_score > previous.raw_score:
                self._arbitration_candidates[model_id] = candidate

        if self._arbitration_remaining == 0 and current:
            self._arbitration_remaining = self.arbitration_frames
        if self._arbitration_remaining:
            self._arbitration_remaining -= 1
            if self._arbitration_remaining == 0:
                return self._finish_arbitration()
        return None
