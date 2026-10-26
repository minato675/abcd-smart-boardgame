from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qna_server.engine import RuleAnswerEngine
from qna_server.engine import normalize_answer_tone
from qna_server.engine import normalize_question
from qna_server.engine import normalize_question_for_game
from qna_server.knowledge import RuleKnowledgeBase


class StreamingAnswerClient:
    def __init__(self) -> None:
        self.stream_calls = 0

    def stream_rule_answer(self, boardgame_name, question, context, players):
        self.stream_calls += 1
        yield "조커는 필요한 숫자와 색을 대신할 수 있습니다."
        yield " 회수한 조커는 같은 턴에 바로 사용해야 합니다."

    def answer_rule_question(self, boardgame_name, question, context, players):
        return "fallback"


class RuleAnswerStreamingTest(unittest.TestCase):
    def test_streaming_answer_emits_complete_sentences(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rule_dir = Path(temp_dir)
            (rule_dir / "rummikub.md").write_text(
                "# 루미큐브\n\n## 최초 등록\n\n처음 타일을 내려놓을 때는 30점 이상이어야 한다.\n",
                encoding="utf-8",
            )
            engine = RuleAnswerEngine(
                RuleKnowledgeBase.load(rule_dir),
                StreamingAnswerClient(),
            )
            spoken: list[str] = []

            answer = engine.answer_streaming(
                "루미큐브",
                "최초 등록은 어떻게 해?",
                4,
                spoken.append,
            )

        self.assertEqual(spoken, [
            "조커는 필요한 숫자와 색을 대신할 수 있습니다.",
            "회수한 조커는 같은 턴에 바로 사용해야 합니다.",
        ])
        self.assertEqual(answer.spoken_sentences, 2)
        self.assertIn("조커는 필요한", answer.text)

    def test_question_normalization_fixes_common_stt_errors(self) -> None:
        self.assertEqual(normalize_question("조카는 어떻겠어?"), "조커는 어떻겠어?")
        self.assertEqual(normalize_question("독화는 어떻게 써?"), "조커는 어떻게 써?")

    def test_halligalli_question_normalization_fixes_common_stt_errors(self) -> None:
        self.assertEqual(
            normalize_question_for_game("할리갈리", "16개일 때 종 쳐도 돼?"),
            "6개일 때 종 쳐도 돼?",
        )
        self.assertEqual(
            normalize_question_for_game("할리갈리", "동 쳐도 돼?"),
            "종 쳐도 돼?",
        )

    def test_answer_tone_normalization_uses_polite_endings(self) -> None:
        self.assertEqual(
            normalize_answer_tone("처음 타일을 내려놓을 때는 가진 타일로 30점 이상 만들어야 한다."),
            "처음 타일을 내려놓을 때는 가진 타일로 30점 이상 만들어야 합니다.",
        )
        self.assertEqual(
            normalize_answer_tone("과일이 6개일 때는 종을 칠 수 없다."),
            "과일이 6개일 때는 종을 칠 수 없습니다.",
        )

    def test_halligalli_bell_question_uses_fast_rule_answer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rule_dir = Path(temp_dir)
            (rule_dir / "halligalli.md").write_text(
                "# 할리갈리\n\n## 종 치기\n\n같은 과일이 정확히 5개일 때만 종을 칠 수 있다.\n",
                encoding="utf-8",
            )
            client = StreamingAnswerClient()
            engine = RuleAnswerEngine(RuleKnowledgeBase.load(rule_dir), client)
            spoken: list[str] = []

            answer = engine.answer_streaming(
                "할리갈리",
                "과일 6개일 때 종 쳐도 돼?",
                4,
                spoken.append,
            )

        self.assertEqual(answer.text, "아니요. 할리갈리는 같은 과일이 정확히 5개일 때만 종을 칠 수 있습니다.")
        self.assertEqual(spoken, ["아니요. 할리갈리는 같은 과일이 정확히 5개일 때만 종을 칠 수 있습니다."])
        self.assertEqual(client.stream_calls, 0)


if __name__ == "__main__":
    unittest.main()
