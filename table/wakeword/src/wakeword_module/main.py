"""Service entry point.  Production startup remains fail-closed on quality."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import signal
import time

from .audio import ExclusiveResourceLocks, SoundDeviceAudioSource
from .config import load_config
from .detector import DetectionStateMachine
from .engine import OpenWakeWordEngine
from .health import JsonLogFormatter
from .manifest import validate_artifacts
from .mqtt import MqttAdapter, WakeTopics
from .coordinator import WakeWordModule
from .worker import InferenceWorker


def configure_logging(level_name: str) -> None:
    """Configure bounded JSON logs for the command-line service."""

    level = getattr(logging, level_name.upper(), None)
    if not isinstance(level, int):
        raise ValueError(f"invalid log level: {level_name}")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)


def run(config_path: str | Path) -> int:
    logger = logging.getLogger("wakeword_module")
    config = load_config(config_path)
    logger.info(
        "configuration_loaded",
        extra={
            "config_path": str(Path(config_path).resolve()),
            "config_revision": config.config_revision,
            "environment": config.environment,
            "room_number": config.room_number,
            "device_id": config.device_id,
        },
    )
    artifact_report = validate_artifacts(config)
    logger.info(
        "artifacts_validated",
        extra={
            "config_revision": artifact_report.config_revision,
            "model_quality": artifact_report.model_quality,
        },
    )
    engine = OpenWakeWordEngine(
        classifier_paths={model.id: model.path for model in config.models},
        melspectrogram_path=config.artifacts.melspectrogram.path,
        embedding_path=config.artifacts.embedding.path,
        vad_path=(
            config.artifacts.vad.path
            if config.artifacts.vad is not None and any(model.vad_mode != "off" for model in config.models)
            else None
        ),
        ncpu=config.runtime.onnx_threads,
    )
    engine.startup_self_test(config.audio.warmup_frames)
    logger.info("engine_self_test_passed")
    detector = DetectionStateMachine(
        config.model_by_id,
        arbitration_frames=config.decision.arbitration_frames,
        collision_margin=config.decision.collision_margin,
        ambiguous_suppression_frames=config.decision.ambiguous_suppression_frames,
        max_vad_history_frames=config.decision.max_vad_history_frames,
    )
    worker = InferenceWorker(
        engine,
        detector,
        warmup_frames=config.audio.warmup_frames,
        queue_blocks=config.audio.queue_blocks,
        max_frame_age_ms=config.audio.max_frame_age_ms,
    )
    audio = SoundDeviceAudioSource(
        device=config.audio.device,
        sample_rate_hz=config.audio.sample_rate_hz,
        channels=config.audio.channels,
        max_callback_samples=config.audio.max_callback_samples,
        sink=worker.offer_audio,
        on_discontinuity=lambda reason, samples: worker.request_discontinuity(reason),
    )
    canonical_device = audio.probe()
    logger.info(
        "audio_device_ready",
        extra={
            "audio_device": canonical_device.name,
            "host_api": canonical_device.host_api,
            "sample_rate_hz": config.audio.sample_rate_hz,
            "channels": config.audio.channels,
        },
    )
    locks = ExclusiveResourceLocks(config.runtime.lock_root, config.room_number, canonical_device.identity)
    locks.acquire()
    # Re-resolve after locking so a volatile selector cannot silently switch
    # to another physical input between enumeration and stream open.
    try:
        locked_device = audio.probe()
    except Exception:
        locks.release()
        raise
    if locked_device.identity != canonical_device.identity:
        locks.release()
        raise RuntimeError("audio device identity changed after exclusive lock acquisition")
    mqtt = MqttAdapter(
        config=config.mqtt,
        topics=WakeTopics(config.room_number),
        contract_version=config.mqtt.contract_version,
        logger=lambda event, fields: logger.debug(event, extra=fields),
    )
    module = WakeWordModule(
        config,
        worker=worker,
        audio_source=audio,
        publisher=mqtt,
        model_quality=artifact_report.model_quality,
    )
    stop_requested = False

    def request_stop(signum: int, frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        logger.info(
            "mqtt_starting",
            extra={"mqtt_host": config.mqtt.host, "mqtt_port": config.mqtt.port},
        )
        mqtt.start()
        module.start(broker_connected=mqtt.connected, ready=artifact_report.production_ready or config.allow_unverified_models)
        logger.info("service_started", extra={"state": module.state.value})
        while not stop_requested:
            for command in mqtt.poll_commands():
                module.handle_message(command)
            module.process_pending()
            if module.broker_connected != mqtt.connected:
                module.set_broker_connected(mqtt.connected)
            time.sleep(0.01)
    finally:
        logger.info("service_stopping", extra={"state": module.state.value})
        module.shutdown()
        mqtt.stop()
        locks.release()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run WakeWordModule")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--log-level",
        type=str.upper,
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default=os.environ.get("WAKEWORD_LOG_LEVEL", "INFO").upper(),
        help="logging verbosity (default: WAKEWORD_LOG_LEVEL or INFO)",
    )
    args = parser.parse_args(argv)
    configure_logging(args.log_level)
    return run(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
