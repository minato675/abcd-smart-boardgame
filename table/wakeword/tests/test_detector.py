from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from wakeword_module.contracts import RawScores
from wakeword_module.detector import DetectionStateMachine, ScoreValidationError


def policies(**overrides):
    base = {
        "ssafiya": SimpleNamespace(id="ssafiya", wire_status="call", trigger_threshold=0.8, evidence_window_frames=1, required_hits=1, vad_mode="off"),
        "nae_teon_kkeutnasseo": SimpleNamespace(id="nae_teon_kkeutnasseo", wire_status="finish", trigger_threshold=0.99, evidence_window_frames=1, required_hits=1, vad_mode="off"),
    }
    base.update(overrides)
    return base


def raw(sequence: int, ssafiya: float, turn: float, *, vad: float | None = None, generation: int = 1) -> RawScores:
    return RawScores(generation, sequence, sequence * 1280, sequence, {"ssafiya": ssafiya, "nae_teon_kkeutnasseo": turn}, vad, datetime(2026, 1, 1, tzinfo=timezone.utc))


class DetectorTests(unittest.TestCase):
    def test_inclusive_threshold_and_one_shot(self) -> None:
        detector = DetectionStateMachine(policies())
        detector.reset(1)
        candidate = detector.feed(raw(0, 0.8, 0.1))
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.wire_status, "call")
        self.assertIsNone(detector.feed(raw(1, 1.0, 1.0)))

    def test_k_of_n_evidence(self) -> None:
        model = SimpleNamespace(id="ssafiya", wire_status="call", trigger_threshold=0.8, evidence_window_frames=3, required_hits=2, vad_mode="off")
        detector = DetectionStateMachine(policies(ssafiya=model))
        detector.reset(1)
        self.assertIsNone(detector.feed(raw(0, 0.81, 0.1)))
        self.assertIsNone(detector.feed(raw(1, 0.2, 0.1)))
        self.assertIsNotNone(detector.feed(raw(2, 0.85, 0.1)))

    def test_dual_candidate_without_margin_is_ambiguous_and_suppresses(self) -> None:
        detector = DetectionStateMachine(policies(), arbitration_frames=1, collision_margin=None, ambiguous_suppression_frames=2)
        detector.reset(1)
        self.assertIsNone(detector.feed(raw(0, 0.9, 0.995)))
        self.assertEqual(detector.suppression_remaining, 2)
        # These high scores cannot accumulate hidden evidence while suppressed.
        self.assertIsNone(detector.feed(raw(1, 1.0, 1.0)))
        self.assertIsNone(detector.feed(raw(2, 1.0, 1.0)))
        self.assertIsNone(detector.feed(raw(3, 0.1, 0.1)))

    def test_score_validation(self) -> None:
        detector = DetectionStateMachine(policies())
        detector.reset(1)
        with self.assertRaises(ScoreValidationError):
            detector.feed(raw(0, float("nan"), 0.0))

    def test_vad_gate_fails_closed_until_context_exists(self) -> None:
        model = SimpleNamespace(id="ssafiya", wire_status="call", trigger_threshold=0.8, evidence_window_frames=1, required_hits=1, vad_mode="gate", vad_threshold=0.5, vad_context_oldest_lag_frames=1, vad_context_newest_lag_frames=0, vad_aggregate="mean")
        detector = DetectionStateMachine(policies(ssafiya=model), max_vad_history_frames=4)
        detector.reset(1)
        self.assertIsNone(detector.feed(raw(0, 0.9, 0.0, vad=0.9)))
        self.assertIsNotNone(detector.feed(raw(1, 0.9, 0.0, vad=0.9)))


if __name__ == "__main__":
    unittest.main()
