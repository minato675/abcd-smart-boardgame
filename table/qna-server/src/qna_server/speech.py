from __future__ import annotations

import logging
import os
import tempfile
import time
import wave
from array import array
from contextlib import suppress
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Protocol

from .gms_client import GmsClient, GmsNoTranscriptError
from .payloads import QnaStartPayload


class SpeechRecognizer(Protocol):
    def recognize(self, start: QnaStartPayload) -> str:
        """Return the user's spoken question as text."""


@dataclass(frozen=True)
class AudioFileSpeechRecognizer:
    client: GmsClient
    audio_file: Path
    transcriber: str = "stt"

    def recognize(self, start: QnaStartPayload) -> str:
        return _transcribe_audio(self.client, self.audio_file, self.transcriber)


@dataclass(frozen=True)
class RecordedAudio:
    path: Path
    heard_speech: bool


@dataclass(frozen=True)
class MicrophoneSpeechRecognizer:
    client: GmsClient
    record_seconds: float
    record_min_seconds: float
    sample_rate: int
    channels: int
    input_device: str
    silence_seconds: float
    silence_threshold: int
    noise_seconds: float
    threshold_multiplier: float
    transcriber: str = "stt"

    def recognize(self, start: QnaStartPayload) -> str:
        attempts = (
            (
                self.record_seconds,
                self.record_min_seconds,
                self.silence_seconds,
                "normal",
            ),
            (
                max(self.record_seconds, 5.5),
                max(self.record_min_seconds, 2.5),
                max(self.silence_seconds, 1.2),
                "retry",
            ),
        )

        last_error: GmsNoTranscriptError | None = None
        for seconds, min_seconds, silence_seconds, label in attempts:
            recording = _record_microphone_wav(
                seconds,
                min_seconds,
                self.sample_rate,
                self.channels,
                self.input_device,
                silence_seconds,
                self.silence_threshold,
                self.noise_seconds,
                self.threshold_multiplier,
            )
            try:
                if not recording.heard_speech:
                    raise GmsNoTranscriptError("Microphone recording had no detected speech.")
                transcript = _transcribe_audio(self.client, recording.path, self.transcriber)
                if _looks_like_invalid_question_transcript(transcript):
                    raise GmsNoTranscriptError(f"Audio transcription returned invalid transcript: {transcript!r}")
                return transcript
            except GmsNoTranscriptError as exc:
                last_error = exc
                if label == "normal":
                    logging.info("Audio transcription returned unusable transcript; retrying with longer recording.")
                    continue
                raise
            finally:
                with suppress(OSError):
                    recording.path.unlink(missing_ok=True)

        if last_error is not None:
            raise last_error
        raise RuntimeError("Microphone STT failed before transcription.")


def build_speech_recognizer(
    mode: str,
    client: GmsClient,
    audio_file: str,
    record_seconds: float,
    record_min_seconds: float,
    sample_rate: int,
    channels: int,
    input_device: str,
    silence_seconds: float,
    silence_threshold: int,
    noise_seconds: float,
    threshold_multiplier: float,
) -> SpeechRecognizer:
    normalized_mode = mode.lower()
    if normalized_mode in {"microphone", "gemini-audio"}:
        transcriber = "gemini-audio" if normalized_mode == "gemini-audio" else "stt"
        return MicrophoneSpeechRecognizer(
            client,
            record_seconds,
            record_min_seconds,
            sample_rate,
            channels,
            input_device,
            silence_seconds,
            silence_threshold,
            noise_seconds,
            threshold_multiplier,
            transcriber,
        )
    if normalized_mode in {"audio-file", "audio-file-gemini"}:
        if not audio_file:
            raise RuntimeError("QNA_AUDIO_FILE is required when QNA_STT_MODE=audio-file")
        transcriber = "gemini-audio" if normalized_mode == "audio-file-gemini" else "stt"
        return AudioFileSpeechRecognizer(client, Path(audio_file), transcriber)
    raise ValueError(f"Unsupported QNA_STT_MODE: {mode}")


def _transcribe_audio(client: GmsClient, audio_path: Path, transcriber: str) -> str:
    if transcriber == "gemini-audio":
        return client.transcribe_audio_with_gemini(audio_path)
    return client.transcribe_audio(audio_path)


def _record_microphone_wav(
    seconds: float,
    min_seconds: float,
    sample_rate: int,
    channels: int,
    input_device: str,
    silence_seconds: float,
    silence_threshold: int,
    noise_seconds: float,
    threshold_multiplier: float,
) -> RecordedAudio:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError(
            "sounddevice is required for microphone STT. Run `pip install -r requirements.txt`."
        ) from exc

    if seconds <= 0:
        raise ValueError("QNA_RECORD_SECONDS must be greater than 0")
    if min_seconds < 0:
        raise ValueError("QNA_RECORD_MIN_SECONDS must be greater than or equal to 0")
    if channels <= 0:
        raise ValueError("QNA_RECORD_CHANNELS must be greater than 0")
    if silence_seconds <= 0:
        raise ValueError("QNA_RECORD_SILENCE_SECONDS must be greater than 0")
    if noise_seconds < 0:
        raise ValueError("QNA_RECORD_NOISE_SECONDS must be greater than or equal to 0")
    if threshold_multiplier <= 0:
        raise ValueError("QNA_RECORD_THRESHOLD_MULTIPLIER must be greater than 0")

    started_at = time.perf_counter()
    frames: list[bytes] = []
    max_frames = int(seconds * sample_rate)
    min_frames = int(min_seconds * sample_rate)
    silence_frame_limit = int(silence_seconds * sample_rate)
    noise_frame_limit = int(noise_seconds * sample_rate)
    remaining = max_frames
    total_frames = 0
    silent_frames = 0
    heard_speech = False
    calibrated_threshold = float(silence_threshold)
    noise_rms_values: list[float] = []
    device, effective_channels, device_label = _resolve_input_stream_settings(sd, input_device, channels)

    with sd.RawInputStream(
        samplerate=sample_rate,
        channels=effective_channels,
        dtype="int16",
        device=device,
    ) as stream:
        while remaining > 0:
            block_size = min(1024, remaining)
            data, overflowed = stream.read(block_size)
            if overflowed:
                # Dropped samples are better than aborting a live kiosk flow.
                pass
            raw_data = bytes(data)
            frames.append(raw_data)
            total_frames += block_size
            remaining -= block_size
            block_rms = _rms_int16(_pcm_int16_to_mono(raw_data, effective_channels))
            if noise_frame_limit and total_frames <= noise_frame_limit:
                noise_rms_values.append(block_rms)
                calibrated_threshold = max(
                    float(silence_threshold),
                    _average(noise_rms_values) * threshold_multiplier,
                )
                continue

            if block_rms >= calibrated_threshold:
                heard_speech = True
                silent_frames = 0
            elif heard_speech:
                silent_frames += block_size

            if (
                heard_speech
                and total_frames >= min_frames
                and silent_frames >= silence_frame_limit
            ):
                break

    fd, output_name = tempfile.mkstemp(prefix="qna-question-", suffix=".wav")
    os.close(fd)
    output = Path(output_name)
    raw_audio = _pcm_int16_to_mono(b"".join(frames), effective_channels)
    enhanced_audio, stt_frames = _suppress_noise_pcm_int16(
        raw_audio,
        sample_rate,
        calibrated_threshold,
    )
    normalized_audio, peak, gain = _normalize_pcm_int16(enhanced_audio)
    with wave.open(str(output), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(normalized_audio)
    logging.info(
        "Microphone recording saved: duration=%.3fs sttDuration=%.3fs channels=%s inputDevice=%s heardSpeech=%s threshold=%.1f peak=%s gain=%.2f elapsed=%.3fs",
        total_frames / sample_rate,
        stt_frames / sample_rate,
        effective_channels,
        device_label,
        heard_speech,
        calibrated_threshold,
        peak,
        gain,
        time.perf_counter() - started_at,
    )
    return RecordedAudio(path=output, heard_speech=heard_speech)


def _parse_input_device(value: str):
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _resolve_input_stream_settings(sd, input_device: str, channels: int):
    requested_device = _parse_input_device(input_device)
    if requested_device is not None:
        try:
            info = sd.query_devices(requested_device)
        except Exception:
            logging.warning(
                "Configured microphone device is unavailable; falling back to default input device: inputDevice=%s",
                input_device,
            )
            return _resolve_default_input_stream_settings(sd, channels)

        max_channels = _max_input_channels(info)
        if max_channels <= 0:
            logging.warning(
                "Configured microphone device has no input channels; falling back to default input device: inputDevice=%s",
                input_device,
            )
            return _resolve_default_input_stream_settings(sd, channels)
        return requested_device, min(channels, max_channels), input_device

    return _resolve_default_input_stream_settings(sd, channels)


def _resolve_default_input_stream_settings(sd, channels: int):
    with suppress(Exception):
        info = sd.query_devices(kind="input")
        max_channels = _max_input_channels(info)
        if max_channels > 0:
            return None, min(channels, max_channels), "<default>"
    return None, channels, "<default>"


def _max_input_channels(device_info) -> int:
    if isinstance(device_info, dict):
        value = device_info.get("max_input_channels", 0)
    else:
        value = getattr(device_info, "max_input_channels", 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _pcm_int16_to_mono(data: bytes, channels: int) -> bytes:
    if channels <= 1 or len(data) < 2:
        return data

    sample_count = len(data) // 2
    frame_count = sample_count // channels
    if frame_count <= 0:
        return b""

    samples = memoryview(data[: frame_count * channels * 2]).cast("h")
    mono = array("h")
    for frame_index in range(frame_count):
        start = frame_index * channels
        total = 0
        for channel_index in range(channels):
            total += samples[start + channel_index]
        mono.append(int(total / channels))
    return mono.tobytes()


def _rms_int16(data: bytes) -> float:
    if len(data) < 2:
        return 0.0
    samples = memoryview(data[: len(data) - (len(data) % 2)]).cast("h")
    if not samples:
        return 0.0
    return sqrt(sum(sample * sample for sample in samples) / len(samples))


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _suppress_noise_pcm_int16(
    data: bytes,
    sample_rate: int,
    threshold: float,
    frame_seconds: float = 0.02,
    padding_seconds: float = 0.25,
    attenuation: float = 0.18,
) -> tuple[bytes, int]:
    sample_count = len(data) // 2
    if sample_count <= 0:
        return data, 0

    samples = array("h")
    samples.frombytes(data[: sample_count * 2])

    frame_size = max(160, int(sample_rate * frame_seconds))
    frame_rms: list[float] = []
    for start in range(0, sample_count, frame_size):
        end = min(sample_count, start + frame_size)
        frame_rms.append(_rms_samples(samples[start:end]))

    gate_threshold = max(180.0, threshold * 0.55)
    speech_frame_indexes = [
        index
        for index, rms in enumerate(frame_rms)
        if rms >= gate_threshold
    ]
    if not speech_frame_indexes:
        return data, sample_count

    padding_frames = max(1, int(padding_seconds / frame_seconds))
    first_frame = max(0, speech_frame_indexes[0] - padding_frames)
    last_frame = min(len(frame_rms), speech_frame_indexes[-1] + padding_frames + 1)
    start_sample = first_frame * frame_size
    end_sample = min(sample_count, last_frame * frame_size)
    trimmed = samples[start_sample:end_sample]

    for frame_index, rms in enumerate(frame_rms[first_frame:last_frame]):
        if rms >= gate_threshold:
            continue
        start = frame_index * frame_size
        end = min(len(trimmed), start + frame_size)
        for sample_index in range(start, end):
            trimmed[sample_index] = int(trimmed[sample_index] * attenuation)

    logging.info(
        "Audio noise suppression applied: gate=%.1f originalDuration=%.3fs sttDuration=%.3fs",
        gate_threshold,
        sample_count / sample_rate,
        len(trimmed) / sample_rate,
    )
    return trimmed.tobytes(), len(trimmed)


def _rms_samples(samples) -> float:
    if not samples:
        return 0.0
    return sqrt(sum(sample * sample for sample in samples) / len(samples))


def _looks_like_invalid_question_transcript(transcript: str) -> bool:
    compact = transcript.strip().replace(" ", "")
    if not compact:
        return True
    if compact in {"끝", "네", "예", "응", "음", "어", "아", "자", "시작", "종료"}:
        return True
    if _contains_stt_hallucination_phrase(compact):
        return True
    if compact.rstrip("!?.。？！") in {"안녕", "안녕하세요", "하이", "헬로"}:
        return True
    return len(compact) <= 1


def _contains_stt_hallucination_phrase(compact_transcript: str) -> bool:
    hallucination_phrases = (
        "네알겠습니다",
        "알겠습니다",
        "오케이",
        "해볼게요",
        "틀어볼게요",
        "리눅스",
        "감사합니다",
        "자막",
        "시청해주셔서",
        "구독",
        "좋아요",
    )
    return any(phrase in compact_transcript for phrase in hallucination_phrases)


def _normalize_pcm_int16(data: bytes, target_peak: int = 26000, max_gain: float = 4.0) -> tuple[bytes, int, float]:
    if len(data) < 2:
        return data, 0, 1.0

    sample_count = len(data) // 2
    samples = memoryview(data[: sample_count * 2]).cast("h")
    peak = max((abs(sample) for sample in samples), default=0)
    if peak <= 0:
        return data, peak, 1.0

    gain = min(max_gain, target_peak / peak)
    if gain <= 1.05:
        return data, peak, 1.0

    amplified = bytearray(sample_count * 2)
    output = memoryview(amplified).cast("h")
    for index, sample in enumerate(samples):
        value = int(sample * gain)
        output[index] = max(-32768, min(32767, value))
    return bytes(amplified), peak, gain
