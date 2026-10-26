from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

from .knowledge import RuleChunk, RuleKnowledgeBase, game_keys_for


INDEX_VERSION = 1


class EmbeddingClient(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector for each input text."""


@dataclass(frozen=True)
class VectorEntry:
    game_key: str
    title: str
    text: str
    embedding: list[float]

    @property
    def chunk(self) -> RuleChunk:
        return RuleChunk(game_key=self.game_key, title=self.title, text=self.text)


class RuleVectorStore:
    def __init__(self, entries: list[VectorEntry], embedding_client: EmbeddingClient) -> None:
        self._entries = entries
        self._embedding_client = embedding_client

    @classmethod
    def load_or_build(
        cls,
        knowledge_base: RuleKnowledgeBase,
        index_path: Path,
        embedding_model: str,
        embedding_client: EmbeddingClient,
    ) -> "RuleVectorStore":
        chunks = knowledge_base.chunks
        source_hash = _source_hash(chunks)
        cached_entries = _load_cached_entries(index_path, embedding_model, source_hash)
        if cached_entries is not None:
            logging.info("VectorDB loaded: path=%s entries=%s", index_path, len(cached_entries))
            return cls(cached_entries, embedding_client)

        entries = _build_entries(chunks, embedding_client)
        _save_entries(index_path, embedding_model, source_hash, entries)
        logging.info("VectorDB built: path=%s entries=%s", index_path, len(entries))
        return cls(entries, embedding_client)

    def search(self, boardgame_name: str, question: str, limit: int = 3) -> list[RuleChunk]:
        if not self._entries:
            return []

        game_keys = game_keys_for(boardgame_name)
        target_entries = [entry for entry in self._entries if entry.game_key in game_keys]
        if not target_entries:
            target_entries = [entry for entry in self._entries if entry.game_key == "default"]
        if not target_entries:
            return []

        query_embeddings = self._embedding_client.embed_texts([question])
        if not query_embeddings:
            return []
        query_embedding = query_embeddings[0]

        scored = [
            (_cosine_similarity(query_embedding, entry.embedding), entry)
            for entry in target_entries
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry.chunk for score, entry in scored[:limit] if score > 0]


class QdrantApi(Protocol):
    def collection_exists(self) -> bool:
        """Return whether the configured Qdrant collection exists."""

    def recreate_collection(self, vector_size: int) -> None:
        """Recreate the configured collection with the given vector size."""

    def get_payload(self, point_id: str) -> dict[str, Any] | None:
        """Return one point payload by id, if it exists."""

    def upsert_points(self, points: list[dict[str, Any]]) -> None:
        """Insert or update points in the configured collection."""

    def search(self, vector: list[float], limit: int) -> list[dict[str, Any]]:
        """Return payloads for the closest points."""


class QdrantRuleVectorStore:
    def __init__(
        self,
        embedding_client: EmbeddingClient,
        qdrant: QdrantApi,
    ) -> None:
        self._embedding_client = embedding_client
        self._qdrant = qdrant

    @classmethod
    def load_or_build(
        cls,
        knowledge_base: RuleKnowledgeBase,
        embedding_model: str,
        embedding_client: EmbeddingClient,
        qdrant: QdrantApi,
    ) -> "QdrantRuleVectorStore":
        chunks = knowledge_base.chunks
        source_hash = _source_hash(chunks)
        metadata_id = _metadata_point_id()

        if qdrant.collection_exists():
            metadata = qdrant.get_payload(metadata_id)
            if (
                metadata
                and metadata.get("kind") == "metadata"
                and metadata.get("sourceHash") == source_hash
                and metadata.get("embeddingModel") == embedding_model
            ):
                logging.info("Qdrant VectorDB loaded: chunks=%s", metadata.get("chunkCount"))
                return cls(embedding_client, qdrant)

        entries = _build_entries(chunks, embedding_client)
        if not entries:
            logging.info("Qdrant VectorDB skipped: no rule chunks.")
            return cls(embedding_client, qdrant)

        vector_size = len(entries[0].embedding)
        qdrant.recreate_collection(vector_size)
        qdrant.upsert_points(_qdrant_points(entries, metadata_id, source_hash, embedding_model))
        logging.info("Qdrant VectorDB built: entries=%s vectorSize=%s", len(entries), vector_size)
        return cls(embedding_client, qdrant)

    def search(self, boardgame_name: str, question: str, limit: int = 3) -> list[RuleChunk]:
        query_embeddings = self._embedding_client.embed_texts([question])
        if not query_embeddings:
            return []
        payloads = self._qdrant.search(query_embeddings[0], limit=max(limit * 8, 24))
        game_keys = game_keys_for(boardgame_name)
        chunks: list[RuleChunk] = []
        for payload in payloads:
            if payload.get("kind") != "rule_chunk":
                continue
            game_key = str(payload.get("gameKey", ""))
            if game_key not in game_keys and game_key != "default":
                continue
            title = str(payload.get("title", ""))
            text = str(payload.get("text", ""))
            if game_key and title and text:
                chunks.append(RuleChunk(game_key=game_key, title=title, text=text))
            if len(chunks) >= limit:
                break
        return chunks


class QdrantHttpClient:
    def __init__(
        self,
        base_url: str,
        collection: str,
        api_key: str = "",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not base_url:
            raise RuntimeError("QDRANT_URL is required when QNA_VECTOR_BACKEND=qdrant.")
        if not collection:
            raise RuntimeError("QDRANT_COLLECTION is required when QNA_VECTOR_BACKEND=qdrant.")
        self._base_url = base_url.rstrip("/")
        self._collection = collection
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def collection_exists(self) -> bool:
        response = self._request("GET", self._collection_url(), allow_not_found=True)
        return response is not None

    def recreate_collection(self, vector_size: int) -> None:
        self._request("DELETE", self._collection_url(), allow_not_found=True)
        self._request(
            "PUT",
            self._collection_url(),
            json_body={"vectors": {"size": vector_size, "distance": "Cosine"}},
        )

    def get_payload(self, point_id: str) -> dict[str, Any] | None:
        response = self._request(
            "POST",
            f"{self._collection_url()}/points",
            json_body={
                "ids": [point_id],
                "with_payload": True,
                "with_vector": False,
            },
            allow_not_found=True,
        )
        if response is None:
            return None
        result = response.get("result")
        if isinstance(result, list) and result:
            payload = result[0].get("payload")
            if isinstance(payload, dict):
                return payload
        return None

    def upsert_points(self, points: list[dict[str, Any]]) -> None:
        if not points:
            return
        self._request(
            "PUT",
            f"{self._collection_url()}/points",
            params={"wait": "true"},
            json_body={"points": points},
        )

    def search(self, vector: list[float], limit: int) -> list[dict[str, Any]]:
        response = self._request(
            "POST",
            f"{self._collection_url()}/points/search",
            json_body={
                "vector": vector,
                "limit": limit,
                "with_payload": True,
                "with_vector": False,
            },
        )
        result = response.get("result")
        if not isinstance(result, list):
            return []
        payloads: list[dict[str, Any]] = []
        for item in result:
            if isinstance(item, dict) and isinstance(item.get("payload"), dict):
                payloads.append(item["payload"])
        return payloads

    def _collection_url(self) -> str:
        return f"{self._base_url}/collections/{quote(self._collection, safe='')}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["api-key"] = self._api_key
        return headers

    def _request(
        self,
        method: str,
        url: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        allow_not_found: bool = False,
    ) -> dict[str, Any] | None:
        import requests

        response = requests.request(
            method,
            url,
            headers=self._headers(),
            json=json_body,
            params=params,
            timeout=self._timeout_seconds,
        )
        if allow_not_found and response.status_code == 404:
            return None
        if not response.ok:
            body = response.text.strip()
            if len(body) > 1000:
                body = body[:1000] + "..."
            raise RuntimeError(
                f"Qdrant request failed: {response.status_code} {response.reason} "
                f"for {response.url}. Response body: {body or '<empty>'}"
            )
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"Qdrant returned non-object JSON: {data}")
        return data


def _build_entries(chunks: list[RuleChunk], embedding_client: EmbeddingClient) -> list[VectorEntry]:
    texts = [_embedding_text(chunk) for chunk in chunks]
    embeddings = embedding_client.embed_texts(texts)
    if len(embeddings) != len(chunks):
        raise RuntimeError(f"Embedding count mismatch: chunks={len(chunks)} embeddings={len(embeddings)}")
    return [
        VectorEntry(
            game_key=chunk.game_key,
            title=chunk.title,
            text=chunk.text,
            embedding=embedding,
        )
        for chunk, embedding in zip(chunks, embeddings)
    ]


def _qdrant_points(
    entries: list[VectorEntry],
    metadata_id: str,
    source_hash: str,
    embedding_model: str,
) -> list[dict[str, Any]]:
    vector_size = len(entries[0].embedding) if entries else 0
    points = [
        {
            "id": metadata_id,
            "vector": [0.0] * vector_size,
            "payload": {
                "kind": "metadata",
                "sourceHash": source_hash,
                "embeddingModel": embedding_model,
                "chunkCount": len(entries),
            },
        }
    ]
    for entry in entries:
        points.append(
            {
                "id": _chunk_point_id(entry),
                "vector": entry.embedding,
                "payload": {
                    "kind": "rule_chunk",
                    "gameKey": entry.game_key,
                    "title": entry.title,
                    "text": entry.text,
                    "sourceHash": source_hash,
                    "embeddingModel": embedding_model,
                },
            }
        )
    return points


def _load_cached_entries(index_path: Path, embedding_model: str, source_hash: str) -> list[VectorEntry] | None:
    if not index_path.exists():
        return None
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if data.get("version") != INDEX_VERSION:
        return None
    if data.get("embeddingModel") != embedding_model:
        return None
    if data.get("sourceHash") != source_hash:
        return None

    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        return None

    entries: list[VectorEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            return None
        embedding = raw_entry.get("embedding")
        if not isinstance(embedding, list):
            return None
        entries.append(
            VectorEntry(
                game_key=str(raw_entry.get("gameKey", "")),
                title=str(raw_entry.get("title", "")),
                text=str(raw_entry.get("text", "")),
                embedding=[float(value) for value in embedding],
            )
        )
    return entries


def _save_entries(
    index_path: Path,
    embedding_model: str,
    source_hash: str,
    entries: list[VectorEntry],
) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": INDEX_VERSION,
        "embeddingModel": embedding_model,
        "sourceHash": source_hash,
        "entries": [
            {
                "gameKey": entry.game_key,
                "title": entry.title,
                "text": entry.text,
                "embedding": entry.embedding,
            }
            for entry in entries
        ],
    }
    index_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _source_hash(chunks: list[RuleChunk]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk.game_key.encode("utf-8"))
        digest.update(b"\0")
        digest.update(chunk.title.encode("utf-8"))
        digest.update(b"\0")
        digest.update(chunk.text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _embedding_text(chunk: RuleChunk) -> str:
    return f"게임: {chunk.game_key}\n제목: {chunk.title}\n내용: {chunk.text}"


def _metadata_point_id() -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "qna-server:metadata:boardgame-rules"))


def _chunk_point_id(entry: VectorEntry) -> str:
    digest = hashlib.sha256()
    digest.update(entry.game_key.encode("utf-8"))
    digest.update(b"\0")
    digest.update(entry.title.encode("utf-8"))
    digest.update(b"\0")
    digest.update(entry.text.encode("utf-8"))
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"qna-server:rule-chunk:{digest.hexdigest()}"))


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
