from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.core.vector_indexing import (
    TextChunk,
    chunk_text,
    index_file,
)
from agent.core.vector_store import VectorStore


class VectorIndexingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)
        (self.root / "tests").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:  # pragma: no cover - cleanup
        self.tmpdir.cleanup()

    def test_chunk_text_respects_overlap(self) -> None:
        text = "abcdefghij"
        chunks = chunk_text(text, chunk_size=4, overlap=1)
        self.assertIsInstance(chunks[0], TextChunk)
        contents = [chunk.text for chunk in chunks]
        self.assertEqual(contents, ["abcd", "defg", "ghij"])
        self.assertEqual(chunks[1].start, 3)
        self.assertEqual(chunks[1].end, 7)

    def test_index_file_populates_metadata(self) -> None:
        target = self.root / "docs" / "guide.md"
        target.write_text("First line\nSecond line\n", encoding="utf-8")
        store_path = self.root / "state" / "vector_store.json"
        vector_store = VectorStore(store_path)

        chunk_total = index_file(vector_store, target, root=self.root, chunk_size=16, overlap=4)
        self.assertGreater(chunk_total, 0)
        vector_store.save()

        payload = json.loads(store_path.read_text(encoding="utf-8"))
        records = payload.get("records", [])
        self.assertEqual(len(records), chunk_total)
        first = records[0]
        self.assertEqual(first["metadata"]["path"], "docs/guide.md")
        self.assertEqual(first["metadata"]["chunk_count"], chunk_total)


class VectorStoreRefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        docs = self.root / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        (self.root / "tests").mkdir(parents=True, exist_ok=True)
        self.doc_path = docs / "manual.md"
        self.doc_path.write_text("Alpha\nBeta\nGamma", encoding="utf-8")
        self.store_path = self.root / "state" / "vector_store.json"
        self.vector_store = VectorStore(self.store_path)

    def tearDown(self) -> None:  # pragma: no cover - cleanup
        self.tmpdir.cleanup()

    def test_refresh_vector_cache_updates_docs(self) -> None:
        from agent.core.task_selection import refresh_vector_cache

        updated = refresh_vector_cache(
            self.vector_store,
            touched_paths=[str(self.doc_path)],
            root=self.root,
            chunk_size=12,
            overlap=2,
        )
        self.assertEqual(updated, ["docs/manual.md"])
        payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        self.assertTrue(payload["records"])
        for record in payload["records"]:
            self.assertEqual(record["metadata"]["path"], "docs/manual.md")

