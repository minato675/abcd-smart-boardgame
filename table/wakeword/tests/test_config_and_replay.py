from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import unittest
from dataclasses import replace

from pathlib import Path
import tempfile
import wave
from wakeword_module.config import load_config
from wakeword_module.manifest import validate_artifacts
from wakeword_module.manifest import main as validate_artifacts_main
from wakeword_module.manifest import ArtifactValidationError
from wakeword_module.replay import convert_wav


class ConfigReplayTests(unittest.TestCase):
    def test_current_artifacts_are_hash_checked_but_unverified(self) -> None:
        config = load_config("config/development.yaml")
        report = validate_artifacts(config)
        self.assertFalse(report.production_ready)
        self.assertEqual(report.model_quality, "unverified")
        self.assertEqual(report.artifact_hashes["ssafiya"], config.model_by_id["ssafiya"].sha256)
    def test_manifest_cli_allow_unverified_flag(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            result = validate_artifacts_main(
                ["--config", "config/development.yaml", "--allow-unverified"]
            )
        self.assertEqual(result, 0)
        self.assertIn('"ok": true', output.getvalue())


    def test_wav_conversion_is_explicit_and_mono_16k(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = Path(temp_dir) / "fixture.wav"
            with wave.open(str(fixture), "wb") as writer:
                writer.setnchannels(2)
                writer.setsampwidth(2)
                writer.setframerate(44100)
                writer.writeframes(bytes(4410 * 2 * 2))
            pcm, metadata = convert_wav(fixture)
        self.assertEqual(metadata.source_rate_hz, 44100)
        self.assertEqual(metadata.source_channels, 2)
        self.assertEqual(metadata.resample_up, 160)
        self.assertEqual(metadata.resample_down, 441)
        self.assertEqual(pcm.dtype.name, "int16")

    def test_production_refuses_current_quality_evidence(self) -> None:
        config = load_config("config/development.yaml")
        with self.assertRaises((ArtifactValidationError, ValueError)):
            production = replace(config, environment="production", allow_unverified_models=False)
            validate_artifacts(production)


if __name__ == "__main__":
    unittest.main()
