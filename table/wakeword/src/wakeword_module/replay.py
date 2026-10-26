"""Production-path offline WAV replay and phase-offset diagnostics."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from math import gcd
from pathlib import Path
import json
import time
from typing import Any

import numpy as np
import scipy.signal
import soundfile as sf

from .config import WakeWordConfig, load_config
from .engine import OpenWakeWordEngine
from .framing import PcmFrameAssembler
from .contracts import AudioBlock
from .manifest import validate_artifacts


@dataclass(frozen=True, slots=True)
class ConvertedAudio:
    source_rate_hz: int
    source_channels: int
    source_frames: int
    source_subtype: str
    resample_up: int
    resample_down: int
    pcm_samples: int


@dataclass(frozen=True, slots=True)
class ClipReplay:
    path: str
    expected_model: str
    expected_threshold: float
    converted: ConvertedAudio
    frame_count: int
    max_scores: dict[str, float]
    crossed: dict[str, bool]
    duplicate_events: int
    fragments_seed: int
    smoke_pass: bool


def convert_wav(path: str | Path) -> tuple[np.ndarray, ConvertedAudio]:
    source_path = Path(path)
    try:
        audio, source_rate = sf.read(source_path, dtype="float32", always_2d=True)
        info = sf.info(source_path)
    except Exception as exc:
        raise RuntimeError(f"cannot read WAV metadata/audio: {source_path}") from exc
    mono = audio.mean(axis=1, dtype=np.float64).astype(np.float32)
    divisor = gcd(16000, int(source_rate))
    up = 16000 // divisor
    down = int(source_rate) // divisor
    mono_16k = scipy.signal.resample_poly(mono, up, down)
    pcm16 = np.clip(np.rint(mono_16k * 32768.0), -32768, 32767).astype(np.int16)
    metadata = ConvertedAudio(
        source_rate_hz=int(source_rate),
        source_channels=int(info.channels),
        source_frames=int(info.frames),
        source_subtype=str(info.subtype),
        resample_up=up,
        resample_down=down,
        pcm_samples=int(pcm16.size),
    )
    return pcm16, metadata


def _expected_model(path: Path) -> str:
    if path.name.startswith("ssafiya_"):
        return "ssafiya"
    if path.name.startswith("turn_"):
        return "nae_teon_kkeutnasseo"
    raise ValueError(f"cannot infer expected model from fixture name: {path.name}")


def _stream_frames(engine: OpenWakeWordEngine, samples: np.ndarray, *, generation: int, fragments_seed: int) -> tuple[list[dict[str, float]], int]:
    assembler = PcmFrameAssembler(generation=generation)
    predictions: list[dict[str, float]] = []
    rng = np.random.default_rng(fragments_seed)
    offset = 0
    sample_clock = 0
    callback_ns = time.monotonic_ns()
    while offset < samples.size:
        remaining = int(samples.size - offset)
        # Deliberately exercise arbitrary callback fragmentation, including
        # blocks that yield multiple exact model frames.
        if remaining > 4096:
            size = int(rng.integers(1, 4097))
        else:
            size = remaining
        chunk = samples[offset : offset + size]
        block = AudioBlock(generation, sample_clock, callback_ns, None, chunk.astype("<i2", copy=False).tobytes())
        for frame in assembler.append(block):
            predictions.append(dict(engine.predict(frame.pcm).scores))
        offset += size
        sample_clock += size
        callback_ns += 1_000_000
    assembler.discard_tail()
    return predictions, int(assembler.stats.discarded_tail_samples)


def replay_clip(config: WakeWordConfig, engine: OpenWakeWordEngine, path: str | Path, *, fragments_seed: int = 1) -> ClipReplay:
    clip_path = Path(path)
    pcm, metadata = convert_wav(clip_path)
    expected = _expected_model(clip_path)
    threshold = config.model_by_id[expected].trigger_threshold
    padded = np.concatenate((np.zeros(16000, dtype=np.int16), pcm, np.zeros(16000, dtype=np.int16)))
    engine.reset_and_warm(config.audio.warmup_frames)
    predictions, _tail = _stream_frames(engine, padded, generation=0, fragments_seed=fragments_seed)
    max_scores = {
        model_id: max((float(prediction[model_id]) for prediction in predictions), default=0.0)
        for model_id in config.model_by_id
    }
    crossed = {
        model_id: any(prediction[model_id] >= config.model_by_id[model_id].trigger_threshold for prediction in predictions)
        for model_id in config.model_by_id
    }
    smoke_pass = (
        crossed[expected]
        and not any(value for model_id, value in crossed.items() if model_id != expected)
        and len(predictions) > 0
    )
    return ClipReplay(
        path=str(clip_path),
        expected_model=expected,
        expected_threshold=threshold,
        converted=metadata,
        frame_count=len(predictions),
        max_scores=max_scores,
        crossed=crossed,
        duplicate_events=0,
        fragments_seed=fragments_seed,
        smoke_pass=smoke_pass,
    )


def phase_sweep(config: WakeWordConfig, engine: OpenWakeWordEngine, path: str | Path, *, step: int = 1) -> dict[str, Any]:
    if not 1 <= step <= 1279:
        raise ValueError("phase sweep step must be between 1 and 1,279")
    clip_path = Path(path)
    pcm, metadata = convert_wav(clip_path)
    expected = _expected_model(clip_path)
    threshold = config.model_by_id[expected].trigger_threshold
    scores: list[float] = []
    phases = list(range(0, 1280, step))
    # One true reset/warm establishes the exact starting state.  Restoring
    # that state is equivalent for this diagnostic and avoids 1,280 repeated
    # randomized frontend initializations; live service paths never use it.
    engine.reset_and_warm(config.audio.warmup_frames)
    warm_state = engine.snapshot_warm_state()
    for phase in phases:
        padded = np.concatenate((np.zeros(16000 + phase, dtype=np.int16), pcm, np.zeros(16000, dtype=np.int16)))
        engine.restore_warm_state(warm_state)
        predictions, _ = _stream_frames(engine, padded, generation=phase + 1, fragments_seed=phase + 17)
        scores.append(max((prediction[expected] for prediction in predictions), default=0.0))
    values = np.asarray(scores, dtype=np.float64)
    return {
        "path": str(clip_path),
        "expected_model": expected,
        "threshold": threshold,
        "metadata": asdict(metadata),
        "phase_step_samples": step,
        "phase_count": len(phases),
        "min_score": float(values.min()) if values.size else 0.0,
        "max_score": float(values.max()) if values.size else 0.0,
        "pass_fraction": float(np.mean(values >= threshold)) if values.size else 0.0,
        "pass": bool(values.size and np.all(values >= threshold)),
    }


def build_engine(config: WakeWordConfig) -> OpenWakeWordEngine:
    vad_path = (
        config.artifacts.vad.path
        if config.artifacts.vad is not None and any(model.vad_mode != "off" for model in config.models)
        else None
    )
    return OpenWakeWordEngine(
        classifier_paths={model.id: model.path for model in config.models},
        melspectrogram_path=config.artifacts.melspectrogram.path,
        embedding_path=config.artifacts.embedding.path,
        vad_path=vad_path,
        ncpu=config.runtime.onnx_threads,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay wake-word WAV files through exact production framing")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--input", type=Path, default=Path("test_audio"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--warmup-frames", type=int)
    parser.add_argument("--phase-sweep", action="store_true")
    parser.add_argument("--phase-step", type=int, default=1)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.warmup_frames is not None and args.warmup_frames < 25:
        parser.error("--warmup-frames must be at least 25")
    # This check deliberately keeps the current service in unverified mode;
    # it still validates every loaded artifact hash and ONNX contract.
    artifact_report = validate_artifacts(config)
    engine = build_engine(config)
    paths = [args.input] if args.input.is_file() else sorted(args.input.glob("*.wav"))
    clips = [asdict(replay_clip(config, engine, path, fragments_seed=index + 1)) for index, path in enumerate(paths)]
    report: dict[str, Any] = {
        "configRevision": config.config_revision,
        "artifactHashes": artifact_report.artifact_hashes,
        "modelQuality": artifact_report.model_quality,
        "productionReady": artifact_report.production_ready,
        "validationWarnings": list(artifact_report.warnings),
        "runtime": "pinned-openwakeword-onnx-cpu",
        "clips": clips,
        "offlineSmokePass": all(item["smoke_pass"] for item in clips),
    }
    if args.phase_sweep:
        report["phaseSweep"] = [phase_sweep(config, engine, path, step=args.phase_step) for path in paths]
        report["phaseSweepPass"] = all(item["pass"] for item in report["phaseSweep"])
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
