# Task State Persistence

## Purpose
The automation agent must track which backlog items have already been executed so subsequent runs avoid redundant work. The module `agent/core/task_state.py` provides a small persistence layer around a JSON file on disk.

## Storage Location
- Default path: `state/task_state.json`
- Format: `{\"completed\": [\"task-id-1\", \"task-id-2\"]}` (sorted on write)
- The directory is kept in the repository via `state/.gitkeep`. Files written at runtime can be committed when durable history is desirable.

## API Overview
- `CompletedTaskStore`: loads, queries, and updates the completed task set. It normalises identifiers (trimmed strings) and persists changes immediately.
  - `mark_completed(task_id)`: add a task and write the updated JSON.
  - `mark_incomplete(task_id)`: remove a task if present.
  - `clear()`: reset the state to an empty list.
  - `reload()`: re-read the JSON file from disk.
- `load_completed_tasks(path=None)`: convenience helper that returns the completed identifiers without instantiating a store.
- `TaskStateError`: raised when the JSON payload cannot be parsed or validated.

## Operational Notes
- The store tolerates a missing file by treating it as an empty state.
- Invalid JSON or malformed entries raise `TaskStateError`, allowing the orchestrator to surface actionable diagnostics.
- Identifiers are normalised via `str(value).strip()`; blank strings or `None` raise `ValueError`, preventing silent data loss.
- The write path ensures parent directories exist and serialises with indentation to simplify manual reviews.

## Task Context Integration
`agent.core.task_context.load_task_batch()` and `load_task_prompt()` automatically read completed task identifiers from the state file when callers do not supply them explicitly. Override the default path with the `state_path` argument or provide a `completed` iterable to bypass disk access. This keeps the prompt-building flow aligned with the persisted task history while avoiding redundant plumbing in the orchestrator.

## Follow-Up Ideas
- Broaden the persisted state to capture in-progress tasks, timestamps, or execution metadata.
- Consider transactional updates if concurrent orchestrator runs become a requirement.
- Expose the store via higher-level orchestration APIs once `agent/orchestrator.py` consumes it directly.
