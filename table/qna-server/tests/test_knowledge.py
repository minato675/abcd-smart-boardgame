from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qna_server.knowledge import RuleKnowledgeBase


class RuleKnowledgeBaseTest(unittest.TestCase):
    def test_search_handles_korean_particles(self) -> None:
        knowledge_base = _load_rummikub_rules()

        chunks = knowledge_base.search("루미큐브", "루미큐브에서 조커는 어떻게 써?", limit=3)

        self.assertTrue(any(chunk.title == "조커" for chunk in chunks))

    def test_search_handles_common_stt_misrecognition(self) -> None:
        knowledge_base = _load_rummikub_rules()

        chunks = knowledge_base.search("루미큐브", "조카는 어떻게 써?", limit=3)

        self.assertTrue(any(chunk.title == "조커" for chunk in chunks))

    def test_search_returns_representative_chunks_for_existing_game(self) -> None:
        knowledge_base = _load_rummikub_rules()

        chunks = knowledge_base.search("루미큐브", "이거 가능한 거야?", limit=3)

        self.assertGreater(len(chunks), 0)


def _load_rummikub_rules() -> RuleKnowledgeBase:
    with tempfile.TemporaryDirectory() as temp_dir:
        rule_dir = Path(temp_dir)
        (rule_dir / "rummikub.md").write_text(
            "\n".join(
                [
                    "# 루미큐브",
                    "",
                    "루미큐브는 숫자 타일 조합 게임이다.",
                    "",
                    "## 조커",
                    "",
                    "조커는 필요한 숫자와 색을 대신할 수 있다.",
                ]
            ),
            encoding="utf-8",
        )
        return RuleKnowledgeBase.load(rule_dir)


if __name__ == "__main__":
    unittest.main()
