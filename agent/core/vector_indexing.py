"""Utilities for building and refreshing the documentation/test vector store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from agent.core.vector_store import VectorStore


DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 200
ALLOWED_EXTENSIONS = {
    ".md",
    ".mdx",
    ".rst",
    ".txt",
    ".py",
    ".json",
    ".yaml",
    ".yml",
}
ALLOWED_ROOTS = {"docs", "tests"}


@dataclass(frozen=True, slots=True)
class TextChunk:
    """Represents a deterministic slice of a source document."""

    text: str
    start: int
    end: int


def normalise_newlines(text: str) -> str:
    """Return *text* with Windows/old-Mac newlines normalised to ``\n``."""

    return text.replace("\r\n", "\n").replace("\r", "\n")


def chunk_text(text: str, *, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[TextChunk]:
    """Split *text* into deterministic, optionally overlapping chunks."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    normalised = normalise_newlines(text)
    length = len(normalised)
    if length == 0:
        return []

    step = chunk_size - overlap
    start = 0
    chunks: list[TextChunk] = []
    while start < length:
        end = min(start + chunk_size, length)
        chunk = normalised[start:end]
        chunks.append(TextChunk(text=chunk, start=start, end=end))
        if end == length:
            break
        start = end - overlap
    return chunks


def iter_source_files(root: Path, include: Sequence[str] = tuple(ALLOWED_ROOTS)) -> Iterator[Path]:
    """Yield indexable files under *root* for the requested directory names."""

    for directory in include:
        candidate_root = root / directory
        if not candidate_root.exists() or not candidate_root.is_dir():
            continue
        for path in sorted(candidate_root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            yield path


def _build_snippet_id(relative_path: Path, chunk_index: int) -> str:
    return f"{relative_path.as_posix()}::chunk-{chunk_index + 1:04d}"


def _detect_source(relative_path: Path) -> str:
    try:
        return relative_path.parts[0]
    except IndexError:  # pragma: no cover - defensive guard
        return "unknown"


def index_file(
    vector_store: VectorStore,
    path: Path,
    *,
    root: Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> int:
    """Index *path* into *vector_store*, returning the number of chunks stored."""

    relative = path.relative_to(root)
    if relative.parts[0] not in ALLOWED_ROOTS:
        return 0

    text = path.read_text(encoding="utf-8")
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    chunk_total = len(chunks)
    vector_store.delete_by_path(relative.as_posix())
    source_label = _detect_source(relative)
    for index, chunk in enumerate(chunks):
        metadata = {
            "path": relative.as_posix(),
            "source": source_label,
            "chunk_index": index,
            "chunk_count": chunk_total,
            "char_start": chunk.start,
            "char_end": chunk.end,
        }
        snippet_id = _build_snippet_id(relative, index)
        vector_store.add_text(snippet_id, chunk.text, metadata=metadata)
    return chunk_total


def index_paths(
    vector_store: VectorStore,
    paths: Iterable[Path],
    *,
    root: Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> dict[str, int]:
    """Index the supplied *paths* and return a mapping of path -> chunk count."""

    indexed: dict[str, int] = {}
    for path in sorted(set(paths)):
        if not path.exists() or not path.is_file():
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if relative.parts[0] not in ALLOWED_ROOTS:
            continue
        chunk_total = index_file(
            vector_store,
            path,
            root=root,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        if chunk_total:
            indexed[relative.as_posix()] = chunk_total
    if indexed:
        vector_store.save()
    return indexed


def rebuild_vector_store(
    storage_path: Path,
    *,
    root: Path,
    include: Sequence[str] = tuple(ALLOWED_ROOTS),
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> dict[str, int]:
    """Rebuild the vector store at *storage_path* using repository docs/tests."""

    storage_path.unlink(missing_ok=True)
    vector_store = VectorStore(storage_path)
    indexed: dict[str, int] = {}
    for path in iter_source_files(root, include):
        chunk_total = index_file(
            vector_store,
            path,
            root=root,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        if chunk_total:
            relative = path.relative_to(root).as_posix()
            indexed[relative] = chunk_total
    vector_store.save()
    return indexed


__all__ = [
    "ALLOWED_EXTENSIONS",
    "ALLOWED_ROOTS",
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_SIZE",
    "TextChunk",
    "chunk_text",
    "index_file",
    "index_paths",
    "iter_source_files",
    "normalise_newlines",
    "rebuild_vector_store",
]

