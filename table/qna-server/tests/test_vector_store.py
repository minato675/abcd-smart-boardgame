from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qna_server.knowledge import RuleKnowledgeBase
from qna_server.vector_store import QdrantRuleVectorStore, RuleVectorStore


class FakeEmbeddingClient:
    def __init__(self) -> None:
        self.calls = 0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [_fake_embedding(text) for text in texts]


class FakeQdrantClient:
    def __init__(self) -> None:
        self.exists = False
        self.vector_size: int | None = None
        self.points: dict[str, dict] = {}

    def collection_exists(self) -> bool:
        return self.exists

    def recreate_collection(self, vector_size: int) -> None:
        self.exists = True
        self.vector_size = vector_size
        self.points = {}

    def get_payload(self, point_id: str):
        point = self.points.get(point_id)
        if not point:
            return None
        return point.get("payload")

    def upsert_points(self, points: list[dict]) -> None:
        self.exists = True
        for point in points:
            self.points[str(point["id"])] = point

    def search(self, vector: list[float], limit: int) -> list[dict]:
        scored = []
        for point in self.points.values():
            payload = point.get("payload", {})
            if payload.get("kind") != "rule_chunk":
                continue
            scored.append((_dot(vector, point["vector"]), payload))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [payload for score, payload in scored[:limit] if score > 0]


class RuleVectorStoreTest(unittest.TestCase):
    def test_vector_search_returns_semantic_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rule_dir = root / "rules"
            rule_dir.mkdir()
            (rule_dir / "rummikub.md").write_text(
                "\n".join(
                    [
                        "# 루미큐브",
                        "",
                        "## 조커",
                        "",
                        "조커는 필요한 숫자와 색을 대신할 수 있다.",
                        "",
                        "## 최초 등록",
                        "",
                        "처음 타일을 내려놓을 때는 30점 이상이어야 한다.",
                    ]
                ),
                encoding="utf-8",
            )
            client = FakeEmbeddingClient()
            store = RuleVectorStore.load_or_build(
                RuleKnowledgeBase.load(rule_dir),
                root / "vector-index.json",
                "text-embedding-3-small",
                client,
            )

            chunks = store.search("루미큐브", "대체 타일은 어떻게 써?", limit=1)

        self.assertEqual(chunks[0].title, "조커")

    def test_cached_index_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rule_dir = root / "rules"
            rule_dir.mkdir()
            (rule_dir / "halligalli.md").write_text(
                "# 할리갈리\n\n## 종 치기\n\n같은 과일이 정확히 5개일 때만 종을 칠 수 있다.\n",
                encoding="utf-8",
            )
            index_path = root / "vector-index.json"
            first_client = FakeEmbeddingClient()
            RuleVectorStore.load_or_build(
                RuleKnowledgeBase.load(rule_dir),
                index_path,
                "text-embedding-3-small",
                first_client,
            )
            second_client = FakeEmbeddingClient()
            RuleVectorStore.load_or_build(
                RuleKnowledgeBase.load(rule_dir),
                index_path,
                "text-embedding-3-small",
                second_client,
            )

        self.assertEqual(second_client.calls, 0)

    def test_qdrant_backend_builds_and_searches_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rule_dir = Path(temp_dir) / "rules"
            rule_dir.mkdir()
            (rule_dir / "rummikub.md").write_text(
                "\n".join(
                    [
                        "# 루미큐브",
                        "",
                        "## 조커",
                        "",
                        "조커는 필요한 숫자와 색을 대신할 수 있다.",
                        "",
                        "## 최초 등록",
                        "",
                        "처음 타일을 내려놓을 때는 30점 이상이어야 한다.",
                    ]
                ),
                encoding="utf-8",
            )
            embedding_client = FakeEmbeddingClient()
            qdrant = FakeQdrantClient()
            store = QdrantRuleVectorStore.load_or_build(
                RuleKnowledgeBase.load(rule_dir),
                "text-embedding-3-small",
                embedding_client,
                qdrant,
            )

            chunks = store.search("루미큐브", "대체 타일은 어떻게 써?", limit=1)

        self.assertTrue(qdrant.exists)
        self.assertEqual(qdrant.vector_size, 3)
        self.assertEqual(chunks[0].title, "조커")

    def test_qdrant_backend_reuses_matching_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rule_dir = Path(temp_dir) / "rules"
            rule_dir.mkdir()
            (rule_dir / "halligalli.md").write_text(
                "# 할리갈리\n\n## 종 치기\n\n같은 과일이 정확히 5개일 때만 종을 칠 수 있다.\n",
                encoding="utf-8",
            )
            knowledge_base = RuleKnowledgeBase.load(rule_dir)
            qdrant = FakeQdrantClient()
            QdrantRuleVectorStore.load_or_build(
                knowledge_base,
                "text-embedding-3-small",
                FakeEmbeddingClient(),
                qdrant,
            )
            second_client = FakeEmbeddingClient()
            QdrantRuleVectorStore.load_or_build(
                knowledge_base,
                "text-embedding-3-small",
                second_client,
                qdrant,
            )

        self.assertEqual(second_client.calls, 0)


def _fake_embedding(text: str) -> list[float]:
    if any(word in text for word in ("조커", "대체")):
        return [1.0, 0.0, 0.0]
    if any(word in text for word in ("최초", "30점")):
        return [0.0, 1.0, 0.0]
    if any(word in text for word in ("종", "과일")):
        return [0.0, 0.0, 1.0]
    return [0.1, 0.1, 0.1]


def _dot(left: list[float], right: list[float]) -> float:
    return sum(left_value * right_value for left_value, right_value in zip(left, right))


if __name__ == "__main__":
    unittest.main()
