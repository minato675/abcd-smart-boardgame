"""Exact PCM16 framing owned by the inference worker."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .contracts import AudioBlock, AudioFrame


class FrameDiscontinuity(ValueError):
    """Raised when the sample clock jumps, overlaps, or changes generation."""


class FrameFormatError(ValueError):
    """Raised when an input block is not little-endian PCM16."""


@dataclass(frozen=True, slots=True)
class FramingStats:
    emitted_frames: int = 0
    discarded_tail_samples: int = 0
    discontinuities: int = 0
    dropped_samples: int = 0


class PcmFrameAssembler:
    """Turn arbitrary contiguous PCM16 blocks into only 1,280-sample frames.

    The assembler has no worker thread and no model reference.  Its caller is
    responsible for serializing calls and for resetting it at every audio gap.
    """

    FRAME_SAMPLES = 1280

    def __init__(self, *, generation: int | None = None, frame_samples: int = FRAME_SAMPLES) -> None:
        if frame_samples != self.FRAME_SAMPLES:
            raise ValueError("openWakeWord framing is fixed at 1,280 samples")
        self.generation = generation
        self.frame_samples = frame_samples
        self._buffer = np.empty(0, dtype=np.int16)
        self._buffer_first_sample: int | None = None
        self._next_sample_index: int | None = None
        self._sequence = 0
        self._stats = FramingStats()

    @property
    def stats(self) -> FramingStats:
        return self._stats

    @property
    def tail_samples(self) -> int:
        return int(self._buffer.size)

    @property
    def next_sample_index(self) -> int | None:
        return self._next_sample_index

    def append(self, block: AudioBlock) -> list[AudioFrame]:
        if self.generation is None:
            self.generation = block.generation
        if block.generation != self.generation:
            self._stats = FramingStats(
                emitted_frames=self._stats.emitted_frames,
                discarded_tail_samples=self._stats.discarded_tail_samples,
                discontinuities=self._stats.discontinuities + 1,
                dropped_samples=self._stats.dropped_samples,
            )
            raise FrameDiscontinuity("audio generation changed")
        if len(block.pcm_bytes) % 2:
            raise FrameFormatError("PCM16 block has an odd byte count")
        try:
            samples = np.frombuffer(block.pcm_bytes, dtype="<i2")
        except ValueError as exc:
            raise FrameFormatError("invalid PCM16 bytes") from exc
        if samples.ndim != 1 or samples.size == 0:
            raise FrameFormatError("PCM16 block is empty")
        samples = np.ascontiguousarray(samples, dtype=np.int16)

        if self._next_sample_index is not None and block.first_sample_index != self._next_sample_index:
            self._stats = FramingStats(
                emitted_frames=self._stats.emitted_frames,
                discarded_tail_samples=self._stats.discarded_tail_samples,
                discontinuities=self._stats.discontinuities + 1,
                dropped_samples=self._stats.dropped_samples + abs(block.first_sample_index - self._next_sample_index),
            )
            raise FrameDiscontinuity(
                f"sample clock expected {self._next_sample_index}, got {block.first_sample_index}"
            )
        self._next_sample_index = block.first_sample_index + int(samples.size)
        if self._buffer.size == 0:
            self._buffer_first_sample = block.first_sample_index
        self._buffer = np.concatenate((self._buffer, samples))

        frames: list[AudioFrame] = []
        while self._buffer.size >= self.frame_samples:
            assert self._buffer_first_sample is not None
            first = self._buffer_first_sample
            pcm = self._buffer[: self.frame_samples]
            self._buffer = self._buffer[self.frame_samples :]
            self._buffer_first_sample = first + self.frame_samples
            frames.append(
                AudioFrame(
                    generation=block.generation,
                    sequence=self._sequence,
                    first_sample_index=first,
                    end_sample_index=first + self.frame_samples,
                    frame_end_monotonic_ns=block.callback_monotonic_ns,
                    pcm=pcm,
                )
            )
            self._sequence += 1
        self._stats = FramingStats(
            emitted_frames=self._stats.emitted_frames + len(frames),
            discarded_tail_samples=self._stats.discarded_tail_samples,
            discontinuities=self._stats.discontinuities,
            dropped_samples=self._stats.dropped_samples,
        )
        return frames

    def discard_tail(self) -> int:
        count = int(self._buffer.size)
        if count:
            self._stats = FramingStats(
                emitted_frames=self._stats.emitted_frames,
                discarded_tail_samples=self._stats.discarded_tail_samples + count,
                discontinuities=self._stats.discontinuities,
                dropped_samples=self._stats.dropped_samples,
            )
        self._buffer = np.empty(0, dtype=np.int16)
        self._buffer_first_sample = self._next_sample_index
        return count

    def reset(self, *, generation: int | None = None) -> int:
        discarded = self.discard_tail()
        self.generation = generation
        self._next_sample_index = None
        self._buffer_first_sample = None
        self._sequence = 0
        return discarded
