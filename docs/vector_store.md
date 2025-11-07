# Vector Store Operations

The agent keeps a lightweight embedding cache (`state/vector_store.json`) so it
can retrieve relevant context from documentation and tests. This document covers
how to seed and maintain that cache.

## Initial Seeding

Use the CLI helper to rebuild the cache from scratch whenever the repository is
cloned or the vector store needs a deterministic refresh:

```bash
python -m agent.cli.vector_store rebuild
```

This command removes any existing cache, walks the `docs/` and `tests/`
directories, and writes fresh embeddings using deterministic chunking
(800-character chunks with a 200-character overlap). Each snippet stores
metadata for its source path, chunk index, and character offsets to simplify
troubleshooting.

## Incremental Refresh

When documentation or tests change, refresh their embeddings without touching
the rest of the cache:

```bash
python -m agent.cli.vector_store refresh docs/guide.md tests/test_example.py
```

During normal runs the orchestrator automatically refreshes embeddings for any
`docs/` or `tests/` files touched by the execution plan, so manual refreshes are
rare.

## Recommended Cadence

- **Daily runs:** the orchestrator refreshes touched files automatically.
- **Branch resets or rebases:** run a full rebuild to keep chunk IDs
  deterministic across runs.
- **Large documentation imports:** trigger a rebuild after bulk changes to
  ensure every file is represented.

## Storage Considerations

The store is a JSON file. Keeping it small ensures quick load times:

- Chunking is deterministic, so commits are repeatable.
- The cache only stores `docs/` and `tests/`; avoid adding binaries or other
  large assets to these directories.
- Periodically review `state/vector_store.json` size. If it grows beyond
  acceptable bounds, consider tightening chunk sizes or pruning unused content
  before rebuilding.

