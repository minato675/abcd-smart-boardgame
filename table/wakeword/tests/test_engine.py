from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from wakeword_module.engine import OpenWakeWordEngine


class FakeModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.models = {"ssafiya": object(), "nae_teon_kkeutnasseo": object()}
        self.model_inputs = {key: 16 for key in self.models}
        self.model_outputs = {key: 1 for key in self.models}
        self.calls = []
        self.reset_count = 0

    def predict(self, frame):
        self.calls.append(frame)
        return {"ssafiya": np.float32(0.8), "nae_teon_kkeutnasseo": np.float32(0.1)}

    def reset(self):
        self.reset_count += 1


class EngineTests(unittest.TestCase):
    def test_explicit_frontend_and_raw_predict_only(self) -> None:
        holder = {}

        def factory(**kwargs):
            holder["model"] = FakeModel(**kwargs)
            return holder["model"]

        engine = OpenWakeWordEngine(
            classifier_paths={"ssafiya": Path("ssafiya.onnx"), "nae_teon_kkeutnasseo": Path("nae_teon_kkeutnasseo.onnx")},
            melspectrogram_path=Path("mel.onnx"),
            embedding_path=Path("embedding.onnx"),
            model_factory=factory,
        )
        engine.reset_and_warm(25)
        prediction = engine.predict(np.zeros(1280, dtype=np.int16))
        self.assertAlmostEqual(prediction.scores["ssafiya"], 0.8, places=6)
        self.assertEqual(holder["model"].kwargs["vad_threshold"], 0)
        self.assertEqual(holder["model"].kwargs["melspec_model_path"], str(Path("mel.onnx").resolve()))
        self.assertEqual(holder["model"].kwargs["embedding_model_path"], str(Path("embedding.onnx").resolve()))
        self.assertTrue(all(len(call) == 1280 for call in holder["model"].calls))


if __name__ == "__main__":
    unittest.main()
