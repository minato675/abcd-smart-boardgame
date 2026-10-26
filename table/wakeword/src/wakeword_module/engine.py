"""Single-owner wrapper around the pinned openWakeWord model."""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict, deque
from functools import partial
import math
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from .contracts import MODEL_IDS


class InferenceContractError(RuntimeError):
    pass


def checked_float(value: Any, label: str) -> float:
    if isinstance(value, (list, tuple, np.ndarray)):
        array = np.asarray(value)
        if array.size != 1:
            raise InferenceContractError(f"{label} is not scalar")
        value = array.reshape(-1)[0]
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise InferenceContractError(f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result) or result < -1e-6 or result > 1 + 1e-6:
        raise InferenceContractError(f"{label} is outside [0,1]")
    return min(1.0, max(0.0, result))


@dataclass(frozen=True, slots=True)
class EnginePrediction:
    scores: Mapping[str, float]
    vad_score: float | None = None


class OpenWakeWordEngine:
    """A synchronous engine; callers must use it from one inference worker."""

    def __init__(
        self,
        *,
        classifier_paths: Mapping[str, str | Path],
        melspectrogram_path: str | Path,
        embedding_path: str | Path,
        vad_path: str | Path | None = None,
        ncpu: int = 1,
        model_factory: Callable[..., Any] | None = None,
        vad_factory: Callable[..., Any] | None = None,
    ) -> None:
        if set(classifier_paths) != set(MODEL_IDS):
            raise InferenceContractError("engine requires exactly both configured classifiers")
        self.classifier_paths = {key: Path(value).resolve() for key, value in classifier_paths.items()}
        self.melspectrogram_path = Path(melspectrogram_path).resolve()
        self.embedding_path = Path(embedding_path).resolve()
        self.vad_path = None if vad_path is None else Path(vad_path).resolve()
        self.ncpu = ncpu
        if model_factory is None:
            try:
                from openwakeword.model import Model
            except ImportError as exc:
                raise InferenceContractError("openWakeWord is not installed") from exc
            model_factory = Model
        self.model = model_factory(
            wakeword_models=[str(self.classifier_paths[model_id]) for model_id in MODEL_IDS],
            inference_framework="onnx",
            device="cpu",
            vad_threshold=0,
            enable_speex_noise_suppression=False,
            ncpu=ncpu,
            melspec_model_path=str(self.melspectrogram_path),
            embedding_model_path=str(self.embedding_path),
        )
        self.vad = None
        if self.vad_path is not None:
            if vad_factory is None:
                try:
                    from openwakeword.vad import VAD
                except ImportError as exc:
                    raise InferenceContractError("openWakeWord VAD is not installed") from exc
                vad_factory = VAD
            self.vad = vad_factory(model_path=str(self.vad_path), n_threads=ncpu)
        self._validate_runtime_contract()
        self.warmup_count = 0

    def _validate_runtime_contract(self) -> None:
        model_names = set(getattr(self.model, "models", {}).keys())
        if model_names and model_names != set(MODEL_IDS):
            raise InferenceContractError(f"loaded model IDs do not match configuration: {model_names}")
        inputs = getattr(self.model, "model_inputs", {})
        outputs = getattr(self.model, "model_outputs", {})
        for model_id in MODEL_IDS:
            if inputs and inputs.get(model_id) != 16:
                raise InferenceContractError(f"{model_id} input context is not 16 embeddings")
            if outputs and outputs.get(model_id) != 1:
                raise InferenceContractError(f"{model_id} does not have one output")

    @property
    def loaded_paths(self) -> Mapping[str, str]:
        return {
            **{key: str(value) for key, value in self.classifier_paths.items()},
            "melspectrogram": str(self.melspectrogram_path),
            "embedding": str(self.embedding_path),
            **({"vad": str(self.vad_path)} if self.vad_path else {}),
        }

    @property
    def providers(self) -> tuple[str, ...]:
        values: list[str] = []
        for session in getattr(self.model, "models", {}).values():
            get_providers = getattr(session, "get_providers", None)
            if get_providers is not None:
                values.extend(str(item) for item in get_providers())
        preprocessor = getattr(self.model, "preprocessor", None)
        session = getattr(preprocessor, "melspec_model", None)
        if session is not None and hasattr(session, "get_providers"):
            values.extend(str(item) for item in session.get_providers())
        return tuple(dict.fromkeys(values))

    def _validate_frame(self, frame: np.ndarray) -> np.ndarray:
        value = np.ascontiguousarray(frame, dtype=np.int16)
        if value.shape != (1280,):
            raise InferenceContractError("engine accepts exactly one 1,280-sample frame")
        return value

    def predict(self, frame: np.ndarray) -> EnginePrediction:
        pcm = self._validate_frame(frame)
        # Deliberately pass no patience, threshold, or debounce_time arguments.
        raw = self.model.predict(pcm)
        if not isinstance(raw, Mapping):
            raise InferenceContractError("openWakeWord returned a non-mapping score result")
        scores = {
            model_id: checked_float(raw[model_id], f"score[{model_id}]")
            for model_id in MODEL_IDS
        }
        vad_score = None
        if self.vad is not None:
            vad_score = checked_float(self.vad.predict(pcm, frame_size=640), "vad_score")
        return EnginePrediction(scores=scores, vad_score=vad_score)

    def reset(self) -> None:
        reset = getattr(self.model, "reset", None)
        if reset is None:
            raise InferenceContractError("openWakeWord model has no reset method")
        reset()
        if self.vad is not None:
            reset_states = getattr(self.vad, "reset_states", None)
            if reset_states is None:
                raise InferenceContractError("configured VAD has no reset_states method")
            reset_states()

    def reset_and_warm(self, warmup_frames: int = 25) -> None:
        if warmup_frames < 25:
            raise ValueError("openWakeWord warm-up must contain at least 25 exact frames")
        self.reset()
        silence = np.zeros(1280, dtype=np.int16)
        for _ in range(warmup_frames):
            self.predict(silence)
        self.warmup_count += warmup_frames

    def startup_self_test(self, warmup_frames: int = 25, *, tolerance: float = 1e-5) -> None:
        """Check finite scores and deterministic post-warm silence convergence."""

        silence = np.zeros(1280, dtype=np.int16)
        self.reset_and_warm(warmup_frames)
        first = [self.predict(silence).scores for _ in range(3)]
        self.reset_and_warm(warmup_frames)
        second = [self.predict(silence).scores for _ in range(3)]
        for left, right in zip(first, second):
            for model_id in MODEL_IDS:
                if not math.isfinite(left[model_id]) or not math.isfinite(right[model_id]) or abs(left[model_id] - right[model_id]) > tolerance:
                    raise InferenceContractError("post-warm silence scores do not converge")

    def snapshot_warm_state(self) -> dict[str, Any]:
        """Capture a deterministic post-warm state for offline phase sweeps.

        This is diagnostic-only.  Live start/discontinuity paths always call
        :meth:`reset_and_warm`; the snapshot avoids repeating the pinned
        frontend's expensive randomized initialization 1,280 times while
        comparing frame phase offsets.
        """

        preprocessor = getattr(self.model, "preprocessor", None)
        if preprocessor is None:
            raise InferenceContractError("model has no feature preprocessor")
        return {
            "prediction_buffer": {
                key: tuple(float(value) for value in values)
                for key, values in getattr(self.model, "prediction_buffer", {}).items()
            },
            "preprocessor": {
                "raw_data_buffer": tuple(getattr(preprocessor, "raw_data_buffer", ())),
                "melspectrogram_buffer": np.array(preprocessor.melspectrogram_buffer, copy=True),
                "accumulated_samples": int(preprocessor.accumulated_samples),
                "raw_data_remainder": np.array(preprocessor.raw_data_remainder, copy=True),
                "feature_buffer": np.array(preprocessor.feature_buffer, copy=True),
            },
            "vad": None if self.vad is None else {
                "h": np.array(self.vad._h, copy=True),
                "c": np.array(self.vad._c, copy=True),
                "last_sr": self.vad._last_sr,
                "last_batch_size": self.vad._last_batch_size,
                "prediction_buffer": tuple(float(value) for value in self.vad.prediction_buffer),
            },
        }

    def restore_warm_state(self, snapshot: Mapping[str, Any]) -> None:
        """Restore a state made by :meth:`snapshot_warm_state` for replay only."""

        self.model.prediction_buffer = defaultdict(
            partial(deque, maxlen=30),
            {key: deque(values, maxlen=30) for key, values in snapshot["prediction_buffer"].items()},
        )
        preprocessor = self.model.preprocessor
        preprocessor.raw_data_buffer.clear()
        preprocessor.raw_data_buffer.extend(snapshot["preprocessor"]["raw_data_buffer"])
        preprocessor.melspectrogram_buffer = np.array(snapshot["preprocessor"]["melspectrogram_buffer"], copy=True)
        preprocessor.accumulated_samples = snapshot["preprocessor"]["accumulated_samples"]
        preprocessor.raw_data_remainder = np.array(snapshot["preprocessor"]["raw_data_remainder"], copy=True)
        preprocessor.feature_buffer = np.array(snapshot["preprocessor"]["feature_buffer"], copy=True)
        vad_snapshot = snapshot.get("vad")
        if self.vad is not None and vad_snapshot is not None:
            self.vad._h = np.array(vad_snapshot["h"], copy=True)
            self.vad._c = np.array(vad_snapshot["c"], copy=True)
            self.vad._last_sr = vad_snapshot["last_sr"]
            self.vad._last_batch_size = vad_snapshot["last_batch_size"]
            self.vad.prediction_buffer.clear()
            self.vad.prediction_buffer.extend(vad_snapshot["prediction_buffer"])
