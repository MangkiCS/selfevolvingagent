"""Lightweight vector store with optional FAISS acceleration."""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, MutableMapping, Optional, Sequence


try:  # pragma: no cover - optional dependency
    import faiss  # type: ignore
except Exception:  # pragma: no cover - fallback when FAISS is unavailable
    faiss = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - fallback when NumPy is unavailable
    np = None  # type: ignore


DEFAULT_DIMENSION = 256
STORE_VERSION = 1


class VectorStoreError(RuntimeError):
    """Raised when the vector store cannot complete an operation."""


def _normalise_embedding(values: Sequence[float]) -> List[float]:
    vector = [float(v) for v in values]
    norm = math.sqrt(sum(v * v for v in vector))
    if not norm:
        return [0.0 for _ in vector]
    return [v / norm for v in vector]


def _default_embed(text: str, dimension: int) -> List[float]:
    """Very small hashing-based embedding fallback."""

    cleaned = re.findall(r"\w+", text.lower())
    if not cleaned:
        return [0.0] * dimension
    vector = [0.0] * dimension
    for token in cleaned:
        index = hash(token) % dimension
        vector[index] += 1.0
    return _normalise_embedding(vector)


@dataclass
class VectorRecord:
    """Represents a stored snippet and its embedding."""

    snippet_id: str
    embedding: List[float]
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryResult:
    """Top-k match returned from a similarity search."""

    snippet_id: str
    score: float
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def path(self) -> Optional[str]:
        return self.metadata.get("path")


class VectorStore:
    """Persisted embedding store with optional FAISS support."""

    def __init__(
        self,
        storage_path: os.PathLike[str] | str,
        *,
        embedding_dim: int = DEFAULT_DIMENSION,
        embedding_function: Optional[Callable[[str, int], Sequence[float]]] = None,
        use_faiss: Optional[bool] = None,
    ) -> None:
        self._path = Path(storage_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._default_dim = embedding_dim
        self._embedding_fn = embedding_function or _default_embed
        self._records: MutableMapping[str, VectorRecord] = {}
        self._dimension: Optional[int] = None
        self._dirty = False
        self._use_faiss = use_faiss if use_faiss is not None else bool(faiss and np)
        self._faiss_index = None
        self._faiss_ids: List[str] = []
        self._faiss_dirty = True
        self.load()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def load(self) -> None:
        """Load embeddings from disk if the backing file exists."""

        if not self._path.exists():
            return
        data = json.loads(self._path.read_text(encoding="utf-8"))
        version = data.get("version", 0)
        if version != STORE_VERSION:
            raise VectorStoreError(
                f"Unsupported vector store version {version}; expected {STORE_VERSION}."
            )
        self._dimension = int(data.get("dimension", self._default_dim))
        self._records.clear()
        for item in data.get("records", []):
            embedding = _normalise_embedding(item.get("embedding", []))
            record = VectorRecord(
                snippet_id=str(item["id"]),
                embedding=embedding,
                content=item.get("content", ""),
                metadata=item.get("metadata", {}) or {},
            )
            self._records[record.snippet_id] = record
        self._dirty = False
        self._faiss_dirty = True

    def save(self) -> None:
        """Persist the current store to disk if modified."""

        if not self._dirty:
            return
        payload = {
            "version": STORE_VERSION,
            "dimension": self._dimension or self._default_dim,
            "records": [
                {
                    "id": record.snippet_id,
                    "embedding": record.embedding,
                    "content": record.content,
                    "metadata": record.metadata,
                }
                for record in self._records.values()
            ],
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._dirty = False

    # ------------------------------------------------------------------
    # Mutation API
    # ------------------------------------------------------------------
    def upsert(
        self,
        snippet_id: str,
        embedding: Sequence[float],
        *,
        content: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert or update a snippet embedding."""

        if not embedding:
            raise VectorStoreError("Embedding must contain at least one value")
        normalised = _normalise_embedding(embedding)
        if self._dimension is None:
            self._dimension = len(normalised)
        elif len(normalised) != self._dimension:
            raise VectorStoreError(
                f"Embedding dimensionality mismatch: expected {self._dimension}, got {len(normalised)}"
            )
        record = VectorRecord(
            snippet_id=snippet_id,
            embedding=normalised,
            content=content,
            metadata=metadata or {},
        )
        self._records[snippet_id] = record
        self._dirty = True
        self._faiss_dirty = True

    def add_text(
        self,
        snippet_id: str,
        text: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Convenience helper that embeds and stores raw text."""

        dim = self._dimension or self._default_dim
        embedding = self._embedding_fn(text, dim)
        self.upsert(snippet_id, embedding, content=text, metadata=metadata)

    def bulk_upsert(self, items: Iterable[VectorRecord]) -> None:
        for item in items:
            self.upsert(item.snippet_id, item.embedding, content=item.content, metadata=item.metadata)

    def delete(self, snippet_id: str) -> None:
        if snippet_id in self._records:
            del self._records[snippet_id]
            self._dirty = True
            self._faiss_dirty = True

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------
    def query(self, embedding: Sequence[float], top_k: int = 5) -> List[QueryResult]:
        if not self._records:
            return []
        if self._dimension is None:
            raise VectorStoreError("Vector store is not initialised with any embeddings")
        normalised = _normalise_embedding(embedding)
        if len(normalised) != self._dimension:
            raise VectorStoreError(
                f"Query dimensionality mismatch: expected {self._dimension}, got {len(normalised)}"
            )

        if self._use_faiss and faiss is not None and np is not None:
            return self._query_faiss(normalised, top_k)

        return self._query_python(normalised, top_k)

    def query_text(self, text: str, top_k: int = 5) -> List[QueryResult]:
        if not text.strip():
            return []
        dim = self._dimension or self._default_dim
        embedding = self._embedding_fn(text, dim)
        return self.query(embedding, top_k=top_k)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _query_python(self, embedding: Sequence[float], top_k: int) -> List[QueryResult]:
        scored: List[QueryResult] = []
        for record in self._records.values():
            score = sum(a * b for a, b in zip(embedding, record.embedding))
            scored.append(
                QueryResult(
                    snippet_id=record.snippet_id,
                    score=float(score),
                    content=record.content,
                    metadata=dict(record.metadata),
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]

    def _query_faiss(self, embedding: Sequence[float], top_k: int) -> List[QueryResult]:  # pragma: no cover - optional path
        self._ensure_faiss_index()
        if self._faiss_index is None:
            return self._query_python(embedding, top_k)
        query = np.array([embedding], dtype="float32")
        scores, indices = self._faiss_index.search(query, min(top_k, len(self._faiss_ids)))
        results: List[QueryResult] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            snippet_id = self._faiss_ids[idx]
            record = self._records.get(snippet_id)
            if record is None:
                continue
            results.append(
                QueryResult(
                    snippet_id=snippet_id,
                    score=float(score),
                    content=record.content,
                    metadata=dict(record.metadata),
                )
            )
        return results

    def _ensure_faiss_index(self) -> None:  # pragma: no cover - optional path
        if not self._use_faiss or faiss is None or np is None:
            self._faiss_index = None
            return
        if not self._faiss_dirty and self._faiss_index is not None:
            return
        if not self._records:
            self._faiss_index = None
            self._faiss_ids = []
            self._faiss_dirty = False
            return
        embeddings = np.array(
            [record.embedding for record in self._records.values()], dtype="float32"
        )
        index = faiss.IndexFlatIP(self._dimension or embeddings.shape[1])
        index.add(embeddings)
        self._faiss_index = index
        self._faiss_ids = list(self._records.keys())
        self._faiss_dirty = False


    def delete_where(self, predicate: Callable[[VectorRecord], bool]) -> int:
        """Delete records matching *predicate*, returning the number removed."""

        to_delete = [snippet_id for snippet_id, record in self._records.items() if predicate(record)]
        for snippet_id in to_delete:
            del self._records[snippet_id]
        if to_delete:
            self._dirty = True
            self._faiss_dirty = True
        return len(to_delete)

    def delete_by_path(self, path: str) -> int:
        """Remove all snippets whose ``metadata['path']`` matches *path*.

        Args:
            path: Repository-relative path using forward slashes (``/``).

        Returns:
            The number of snippets removed from the store.
        """

        normalised = path.replace(os.sep, "/")
        return self.delete_where(lambda record: record.metadata.get("path") == normalised)


__all__ = [
    "QueryResult",
    "VectorRecord",
    "VectorStore",
    "VectorStoreError",
    "DEFAULT_DIMENSION",
]

