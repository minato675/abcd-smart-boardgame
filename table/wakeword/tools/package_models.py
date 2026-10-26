"""Build the read-only deployment model bundle from audited artifacts."""

from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import shutil


EXPECTED = {
    "ssafiya.onnx": "af96d0d297eb6bbecbab43debe8af9fff2b914454f55b6ca123b2ba120711641",
    "nae_teon_kkeutnasseo.onnx": "95294f0a98464d3db9b19ad8a07a2d58ed485511757ce5d7583e478c43ae3473",
    "melspectrogram.onnx": "ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f",
    "embedding_model.onnx": "70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f",
    "silero_vad.onnx": "a35ebf52fd3ce5f1469b2a36158dba761bc47b973ea3382b3186ca15b1f5af28",
}


def digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def package(source_root: Path, frontend_root: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in EXPECTED:
        source = source_root / name
        if name in {"melspectrogram.onnx", "embedding_model.onnx", "silero_vad.onnx"}:
            source = frontend_root / name
        if not source.is_file() or source.is_symlink():
            raise RuntimeError(f"missing or unsafe source artifact: {source}")
        actual = digest(source)
        if actual != EXPECTED[name]:
            raise RuntimeError(f"source hash mismatch for {name}: {actual}")
        target = destination / name
        if target.exists() or target.is_symlink():
            if target.is_symlink() or digest(target) != actual:
                raise RuntimeError(f"refusing to overwrite different model bundle file: {target}")
            continue
        shutil.copy2(source, target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path("."))
    parser.add_argument("--frontend-root", type=Path, default=Path("../vendor/openWakeWord/openwakeword/resources/models"))
    parser.add_argument("--destination", type=Path, default=Path("models"))
    args = parser.parse_args(argv)
    package(args.source_root, args.frontend_root, args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
