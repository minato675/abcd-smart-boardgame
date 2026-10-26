"""Reproducible local per-frame benchmark; reports contain no audio."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import time

import numpy as np

from wakeword_module.config import load_config
from wakeword_module.engine import OpenWakeWordEngine
from wakeword_module.manifest import validate_artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--frames", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.frames < 25:
        parser.error("--frames must be at least 25")
    config = load_config(args.config)
    artifact_report = validate_artifacts(config)
    vad_path = config.artifacts.vad.path if config.artifacts.vad and any(m.vad_mode != "off" for m in config.models) else None
    engine = OpenWakeWordEngine(
        classifier_paths={m.id: m.path for m in config.models},
        melspectrogram_path=config.artifacts.melspectrogram.path,
        embedding_path=config.artifacts.embedding.path,
        vad_path=vad_path,
        ncpu=config.runtime.onnx_threads,
    )
    engine.reset_and_warm(config.audio.warmup_frames)
    silence = np.zeros(1280, dtype=np.int16)
    elapsed_ns: list[int] = []
    for _ in range(args.frames):
        started = time.perf_counter_ns()
        engine.predict(silence)
        elapsed_ns.append(time.perf_counter_ns() - started)
    elapsed_ms = np.asarray(elapsed_ns, dtype=np.float64) / 1_000_000
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "configRevision": config.config_revision,
        "modelQuality": artifact_report.model_quality,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "providers": engine.providers,
        "frames": args.frames,
        "frameDurationMs": 80,
        "p50Ms": float(np.percentile(elapsed_ms, 50)),
        "p95Ms": float(np.percentile(elapsed_ms, 95)),
        "p99Ms": float(np.percentile(elapsed_ms, 99)),
        "maxMs": float(elapsed_ms.max()),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
