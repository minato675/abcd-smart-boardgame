from __future__ import annotations

import logging
import math
from array import array
from dataclasses import dataclass
from typing import Protocol


class ReadyCue(Protocol):
    def play_ready(self) -> None:
        """Play a short local cue that tells users they can start speaking."""


@dataclass(frozen=True)
class NoopReadyCue:
    def play_ready(self) -> None:
        return


@dataclass(frozen=True)
class ToneReadyCue:
    enabled: bool
    frequency: int
    duration_seconds: float
    volume: float
    sample_rate: int = 24000
    output_device: str = ""

    def play_ready(self) -> None:
        if not self.enabled:
            return

        try:
            import sounddevice as sd
        except ImportError:
            if _play_windows_beep(self.frequency, self.duration_seconds):
                return
            logging.info("sounddevice is required for ready cue playback.")
            return

        samples = _build_tone_pcm_int16(
            frequency=self.frequency,
            duration_seconds=self.duration_seconds,
            volume=self.volume,
            sample_rate=self.sample_rate,
        )
        device = _parse_output_device(self.output_device)
        try:
            with sd.RawOutputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                device=device,
            ) as stream:
                stream.write(samples)
            logging.info("Ready cue played: frequency=%s duration=%.3fs", self.frequency, self.duration_seconds)
        except Exception:
            logging.exception("Ready cue playback failed.")


def build_ready_cue(
    enabled: bool,
    frequency: int,
    duration_seconds: float,
    volume: float,
    output_device: str,
) -> ReadyCue:
    if not enabled:
        return NoopReadyCue()
    return ToneReadyCue(
        enabled=enabled,
        frequency=frequency,
        duration_seconds=duration_seconds,
        volume=volume,
        output_device=output_device,
    )


def _build_tone_pcm_int16(
    frequency: int,
    duration_seconds: float,
    volume: float,
    sample_rate: int,
) -> bytes:
    if frequency <= 0:
        raise ValueError("QNA_READY_SOUND_FREQUENCY must be greater than 0")
    if duration_seconds <= 0:
        raise ValueError("QNA_READY_SOUND_DURATION_SECONDS must be greater than 0")
    if sample_rate <= 0:
        raise ValueError("Ready cue sample rate must be greater than 0")

    safe_volume = max(0.0, min(1.0, volume))
    sample_count = max(1, int(sample_rate * duration_seconds))
    fade_count = min(sample_count // 2, max(1, int(sample_rate * 0.015)))
    amplitude = int(32767 * safe_volume)
    samples = array("h")

    for index in range(sample_count):
        envelope = 1.0
        if index < fade_count:
            envelope = index / fade_count
        elif index >= sample_count - fade_count:
            envelope = (sample_count - index - 1) / fade_count
        value = int(amplitude * envelope * math.sin(2 * math.pi * frequency * index / sample_rate))
        samples.append(max(-32768, min(32767, value)))

    return samples.tobytes()


def _parse_output_device(value: str):
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _play_windows_beep(frequency: int, duration_seconds: float) -> bool:
    try:
        import winsound
    except ImportError:
        return False
    winsound.Beep(frequency, max(1, int(duration_seconds * 1000)))
    return True
