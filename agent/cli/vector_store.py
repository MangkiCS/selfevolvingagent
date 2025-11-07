"""CLI helpers for managing the repository documentation/test vector store."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from agent.core.vector_indexing import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    ALLOWED_ROOTS,
    index_paths,
    rebuild_vector_store,
)
from agent.core.vector_store import VectorStore


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "state" / "vector_store.json"


def _parse_paths(values: Sequence[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in values:
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path
        paths.append(path)
    return paths


def cmd_rebuild(args: argparse.Namespace) -> int:
    include = tuple(args.include or ALLOWED_ROOTS)
    indexed = rebuild_vector_store(
        Path(args.output),
        root=ROOT,
        include=include,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )
    print(f"Rebuilt vector store with {len(indexed)} files and {sum(indexed.values())} chunks.")
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    paths = _parse_paths(args.paths)
    vector_store = VectorStore(Path(args.output))
    indexed = index_paths(
        vector_store,
        paths,
        root=ROOT,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )
    if indexed:
        print(f"Refreshed {len(indexed)} files: {', '.join(sorted(indexed))}.")
    else:
        print("No matching docs/tests files to refresh.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    rebuild_parser = subparsers.add_parser("rebuild", help="Rebuild the entire vector store")
    rebuild_parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path to the vector store JSON file (default: state/vector_store.json)",
    )
    rebuild_parser.add_argument(
        "--include",
        nargs="*",
        help="Top-level directories to index (default: docs tests)",
    )
    rebuild_parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Maximum characters per chunk",
    )
    rebuild_parser.add_argument(
        "--overlap",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP,
        help="Number of characters to overlap between chunks",
    )
    rebuild_parser.set_defaults(func=cmd_rebuild)

    refresh_parser = subparsers.add_parser(
        "refresh", help="Refresh embeddings for specific files that have changed"
    )
    refresh_parser.add_argument("paths", nargs="+", help="Files to refresh in the vector store")
    refresh_parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path to the vector store JSON file (default: state/vector_store.json)",
    )
    refresh_parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Maximum characters per chunk",
    )
    refresh_parser.add_argument(
        "--overlap",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP,
        help="Number of characters to overlap between chunks",
    )
    refresh_parser.set_defaults(func=cmd_refresh)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    raise SystemExit(main())

