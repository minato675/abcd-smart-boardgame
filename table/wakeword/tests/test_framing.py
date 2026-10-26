from __future__ import annotations

import unittest

import numpy as np

from wakeword_module.contracts import AudioBlock
from wakeword_module.framing import FrameDiscontinuity, PcmFrameAssembler


class FramingTests(unittest.TestCase):
    def test_fragmented_and_batched_blocks_emit_exact_frames(self) -> None:
        samples = np.arange(3000, dtype=np.int16)
        assembler = PcmFrameAssembler(generation=4)
        frames = []
        offset = 0
        for size in (17, 3, 1800, 1180):
            chunk = samples[offset : offset + size]
            if not len(chunk):
                break
            frames.extend(assembler.append(AudioBlock(4, offset, 100 + offset, None, chunk.tobytes())))
            offset += len(chunk)
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].pcm.shape, (1280,))
        np.testing.assert_array_equal(frames[0].pcm, samples[:1280])
        np.testing.assert_array_equal(frames[1].pcm, samples[1280:2560])
        self.assertEqual(assembler.tail_samples, 440)
        self.assertTrue(not frames[0].pcm.flags.writeable)

    def test_gap_is_not_bridged(self) -> None:
        assembler = PcmFrameAssembler(generation=1)
        assembler.append(AudioBlock(1, 0, 1, None, np.zeros(100, dtype=np.int16).tobytes()))
        with self.assertRaises(FrameDiscontinuity):
            assembler.append(AudioBlock(1, 200, 2, None, np.zeros(100, dtype=np.int16).tobytes()))
        self.assertEqual(assembler.stats.discontinuities, 1)

    def test_generation_change_is_rejected(self) -> None:
        assembler = PcmFrameAssembler(generation=1)
        with self.assertRaises(FrameDiscontinuity):
            assembler.append(AudioBlock(2, 0, 1, None, b"\0\0"))


if __name__ == "__main__":
    unittest.main()
