from __future__ import annotations

import logging
import re
import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .gms_client import GmsClient, sanitize_filename


class SpeechSynthesizer(Protocol):
    def speak(self, text: str) -> None:
        """Speak or otherwise output the answer."""


@dataclass(frozen=True)
class PreparedSpeech:
    text: str
    path: Path | None = None


class LoggingSpeechSynthesizer:
    def speak(self, text: str) -> None:
        logging.info("TTS: %s", text)

    def prepare(self, text: str) -> PreparedSpeech:
        logging.info("TTS prepared: %s", text)
        return PreparedSpeech(text=text)

    def play(self, speech: PreparedSpeech) -> None:
        logging.info("TTS: %s", speech.text)


@dataclass(frozen=True)
class GmsSpeechSynthesizer:
    client: GmsClient
    output_dir: Path
    play_audio: bool
    stream_audio: bool
    response_format: str

    @property
    def supports_prefetch(self) -> bool:
        return not self._should_play_live_pcm()

    def speak(self, text: str) -> None:
        if not self._should_play_live_pcm():
            speech = self.prepare(text)
            self.play(speech)
            return

        spoken_text = normalize_tts_text(text)
        if spoken_text != text:
            logging.info("TTS normalized text: %s", spoken_text)
        logging.info("TTS live PCM streaming started: %s", spoken_text)
        audio = self._synthesize(spoken_text, play_live_pcm=True)
        output_path = self._save_audio(text, audio)
        logging.info("TTS streamed audio saved: %s", output_path)

    def prepare(self, text: str) -> PreparedSpeech:
        spoken_text = normalize_tts_text(text)
        if spoken_text != text:
            logging.info("TTS normalized text: %s", spoken_text)
        audio = self._synthesize(spoken_text, play_live_pcm=False)
        output_path = self._save_audio(text, audio)
        logging.info("TTS audio saved: %s", output_path)
        return PreparedSpeech(text=text, path=output_path)

    def _save_audio(self, text: str, audio: bytes) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{sanitize_filename(text[:24])}-{time.time_ns()}.wav"
        _write_audio(output_path, audio, self.response_format)
        return output_path

    def play(self, speech: PreparedSpeech) -> None:
        if self.play_audio and speech.path is not None:
            _play_wav(speech.path)

    def _should_play_live_pcm(self) -> bool:
        return self.stream_audio and self.play_audio and self.response_format.lower() == "pcm"

    def _synthesize(self, text: str, play_live_pcm: bool) -> bytes:
        if not self.stream_audio:
            return self.client.synthesize_speech(text)

        chunks = self.client.stream_speech(text)
        if play_live_pcm and self.play_audio and self.response_format.lower() == "pcm":
            return _play_pcm_stream(chunks)

        if self.play_audio:
            logging.info(
                "TTS HTTP streaming is enabled, but live playback requires "
                "GMS_TTS_RESPONSE_FORMAT=pcm. The completed audio file will be played instead."
            )
        audio = b"".join(chunks)
        if self.play_audio:
            return audio
        return audio


@dataclass(frozen=True)
class ElevenLabsSpeechSynthesizer:
    api_key: str
    base_url: str
    voice_id: str
    model_id: str
    output_format: str
    output_dir: Path
    play_audio: bool
    stream_audio: bool
    stability: float
    similarity_boost: float
    style: float
    use_speaker_boost: bool
    timeout_seconds: float

    @property
    def supports_prefetch(self) -> bool:
        return not self._should_play_live_pcm()

    def speak(self, text: str) -> None:
        if not self._should_play_live_pcm():
            speech = self.prepare(text)
            self.play(speech)
            return

        spoken_text = normalize_tts_text(text)
        if spoken_text != text:
            logging.info("TTS normalized text: %s", spoken_text)
        logging.info("ElevenLabs TTS live PCM streaming started: %s", spoken_text)
        audio = self._synthesize(spoken_text, play_live_pcm=True)
        output_path = self._save_audio(text, audio)
        logging.info("ElevenLabs TTS streamed audio saved: %s", output_path)

    def prepare(self, text: str) -> PreparedSpeech:
        spoken_text = normalize_tts_text(text)
        if spoken_text != text:
            logging.info("TTS normalized text: %s", spoken_text)
        audio = self._synthesize(spoken_text, play_live_pcm=False)
        output_path = self._save_audio(text, audio)
        logging.info("ElevenLabs TTS audio saved: %s", output_path)
        return PreparedSpeech(text=text, path=output_path)

    def play(self, speech: PreparedSpeech) -> None:
        if not self.play_audio or speech.path is None:
            return
        if self._is_pcm_output():
            _play_wav(speech.path)
            return
        logging.info("ElevenLabs audio saved but automatic playback requires PCM output: %s", speech.path)

    def _synthesize(self, text: str, play_live_pcm: bool) -> bytes:
        chunks = self._stream_speech(text)
        if play_live_pcm and self.play_audio and self._is_pcm_output():
            return _play_pcm_stream(chunks, sample_rate=self._pcm_sample_rate())
        return b"".join(chunks)

    def _stream_speech(self, text: str):
        if not self.api_key or self.api_key.startswith("발급받은") or " " in self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY must be set to the real API key.")
        if not self.voice_id:
            raise RuntimeError("ELEVENLABS_VOICE_ID must be set.")

        import requests

        url = f"{self.base_url.rstrip('/')}/v1/text-to-speech/{self.voice_id}/stream"
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
                "style": self.style,
                "use_speaker_boost": self.use_speaker_boost,
            },
        }
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        with requests.post(
            url,
            headers=headers,
            params={"output_format": self.output_format},
            json=payload,
            stream=True,
            timeout=self.timeout_seconds,
        ) as response:
            if not response.ok:
                body = response.text[:1000]
                raise RuntimeError(
                    f"ElevenLabs TTS failed: {response.status_code} {response.reason}. Response body: {body}"
                )
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk

    def _save_audio(self, text: str, audio: bytes) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".wav" if self._is_pcm_output() or audio.startswith(b"RIFF") else ".mp3"
        output_path = self.output_dir / f"{sanitize_filename(text[:24])}-{time.time_ns()}{suffix}"
        if self._is_pcm_output():
            _write_audio(output_path, audio, "pcm", sample_rate=self._pcm_sample_rate())
        else:
            output_path.write_bytes(audio)
        return output_path

    def _should_play_live_pcm(self) -> bool:
        return self.stream_audio and self.play_audio and self._is_pcm_output()

    def _is_pcm_output(self) -> bool:
        return self.output_format.lower().startswith("pcm")

    def _pcm_sample_rate(self) -> int:
        match = re.search(r"pcm_(\d+)", self.output_format.lower())
        if match:
            return int(match.group(1))
        return 24000


class WindowsSpeechSynthesizer:
    def speak(self, text: str) -> None:
        spoken_text = normalize_tts_text(text)
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Speak([Console]::In.ReadToEnd())"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            input=spoken_text,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )


def build_speech_synthesizer(
    mode: str,
    client: GmsClient,
    output_dir: Path,
    play_audio: bool,
    stream_audio: bool,
    response_format: str,
    *,
    elevenlabs_api_key: str = "",
    elevenlabs_base_url: str = "https://api.elevenlabs.io",
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb",
    elevenlabs_model_id: str = "eleven_flash_v2_5",
    elevenlabs_output_format: str = "pcm_24000",
    elevenlabs_stability: float = 0.45,
    elevenlabs_similarity_boost: float = 0.8,
    elevenlabs_style: float = 0.0,
    elevenlabs_use_speaker_boost: bool = True,
    elevenlabs_timeout_seconds: float = 30.0,
) -> SpeechSynthesizer:
    normalized_mode = mode.lower()
    if normalized_mode == "gms":
        return GmsSpeechSynthesizer(client, output_dir, play_audio, stream_audio, response_format)
    if normalized_mode == "elevenlabs":
        return ElevenLabsSpeechSynthesizer(
            api_key=elevenlabs_api_key,
            base_url=elevenlabs_base_url,
            voice_id=elevenlabs_voice_id,
            model_id=elevenlabs_model_id,
            output_format=elevenlabs_output_format,
            output_dir=output_dir,
            play_audio=play_audio,
            stream_audio=stream_audio,
            stability=elevenlabs_stability,
            similarity_boost=elevenlabs_similarity_boost,
            style=elevenlabs_style,
            use_speaker_boost=elevenlabs_use_speaker_boost,
            timeout_seconds=elevenlabs_timeout_seconds,
        )
    if normalized_mode == "log":
        return LoggingSpeechSynthesizer()
    if normalized_mode == "windows":
        return WindowsSpeechSynthesizer()
    raise ValueError(f"Unsupported QNA_TTS_MODE: {mode}")


def normalize_tts_text(text: str) -> str:
    normalized = re.sub(
        r"(\d+)\s*[~-]\s*(\d+)\s*명",
        lambda match: f"{_native_count(int(match.group(1)))} 명에서 {_native_count(int(match.group(2)))} 명",
        text,
    )
    normalized = re.sub(
        r"(\d+)\s*(명|개|장|번|차례)",
        lambda match: f"{_native_count(int(match.group(1)))} {match.group(2)}",
        normalized,
    )
    normalized = re.sub(
        r"(\d+)점",
        lambda match: f"{_sino_number(int(match.group(1)))} 점",
        normalized,
    )
    return re.sub(
        r"(?<![A-Za-z0-9])(\d{1,3})(?![A-Za-z0-9])",
        lambda match: _sino_number(int(match.group(1))),
        normalized,
    )


def _write_audio(output_path: Path, audio: bytes, response_format: str, sample_rate: int = 24000) -> None:
    normalized_format = response_format.lower()
    if audio.startswith(b"RIFF"):
        output_path.write_bytes(_normalize_riff_wav(audio))
        return

    if normalized_format not in {"pcm", "wav"}:
        output_path.write_bytes(audio)
        return

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio)


def _normalize_riff_wav(audio: bytes) -> bytes:
    if len(audio) < 12 or audio[8:12] != b"WAVE":
        return audio

    normalized = bytearray(audio)
    normalized[4:8] = max(0, len(normalized) - 8).to_bytes(4, "little")

    offset = 12
    while offset + 8 <= len(normalized):
        chunk_id = bytes(normalized[offset : offset + 4])
        chunk_size = int.from_bytes(normalized[offset + 4 : offset + 8], "little")
        chunk_data_start = offset + 8

        if chunk_id == b"data":
            actual_data_size = max(0, len(normalized) - chunk_data_start)
            if chunk_size == 0xFFFFFFFF or chunk_data_start + chunk_size > len(normalized):
                normalized[offset + 4 : offset + 8] = actual_data_size.to_bytes(4, "little")
            break

        if chunk_size == 0xFFFFFFFF:
            break
        offset = chunk_data_start + chunk_size + (chunk_size % 2)

    return bytes(normalized)


def _play_wav(path: Path) -> None:
    try:
        import winsound
    except ImportError:
        logging.info("Audio playback is only enabled automatically on Windows: %s", path)
        return
    try:
        winsound.PlaySound(str(path.resolve()), winsound.SND_FILENAME | winsound.SND_NODEFAULT)
    except RuntimeError:
        logging.exception("Cannot play TTS audio automatically: %s", path)


def _play_pcm_stream(chunks, sample_rate: int = 24000) -> bytes:
    try:
        import sounddevice as sd
    except ImportError:
        logging.info("sounddevice is required for live PCM playback. Collecting TTS audio only.")
        return b"".join(chunks)

    collected: list[bytes] = []
    pending = b""
    started_at = time.perf_counter()
    first_chunk_logged = False
    with sd.RawOutputStream(samplerate=sample_rate, channels=1, dtype="int16") as stream:
        for chunk in chunks:
            if not chunk:
                continue
            if not first_chunk_logged:
                logging.info(
                    "TTS PCM first chunk received: elapsed=%.3fs bytes=%s",
                    time.perf_counter() - started_at,
                    len(chunk),
                )
                first_chunk_logged = True
            collected.append(chunk)
            data = pending + chunk
            even_length = len(data) - (len(data) % 2)
            if even_length:
                stream.write(data[:even_length])
            pending = data[even_length:]
    if pending:
        collected.append(pending)
    return b"".join(collected)


def _sino_number(value: int) -> str:
    if value == 0:
        return "영"
    if value < 0:
        return "마이너스 " + _sino_number(abs(value))
    if value >= 1000:
        return str(value)

    units = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
    parts: list[str] = []

    hundreds = value // 100
    tens = (value % 100) // 10
    ones = value % 10

    if hundreds:
        parts.append(("백" if hundreds == 1 else units[hundreds] + "백"))
    if tens:
        parts.append(("십" if tens == 1 else units[tens] + "십"))
    if ones:
        parts.append(units[ones])

    return "".join(parts)


def _native_count(value: int) -> str:
    counts = {
        1: "한",
        2: "두",
        3: "세",
        4: "네",
        5: "다섯",
        6: "여섯",
        7: "일곱",
        8: "여덟",
        9: "아홉",
        10: "열",
    }
    return counts.get(value, _sino_number(value))
