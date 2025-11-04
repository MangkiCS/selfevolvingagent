# Task Specification (`TaskSpec`)

## Purpose

`TaskSpec` provides a structured description of work items that the automation agent can plan and execute. The data model lives in `agent/core/taskspec.py` and is designed to be serialisable so task definitions can be persisted on disk or exchanged via APIs.

## Field Reference

| Field | Type | Required | Description |
| ----- | ---- | -------- | ----------- |
| `task_id` | `str` | Yes | Stable identifier for the task (e.g., `planning/task-loader`). |
| `title` | `str` | Yes | Short, human-readable label used in logs and reports. |
| `summary` | `str` | Yes | One-paragraph overview of the requested change. |
| `details` | `Optional[str]` | No | Additional context, rationale, or implementation hints. |
| `context` | `List[str]` | No | References to relevant files, documents, or external resources. |
| `acceptance_criteria` | `List[str]` | No | Concrete verifications that must pass for the task to be considered done. |
| `priority` | "low" \| "medium" \| "high" \| "critical" | No | Relative urgency used for scheduling. |
| `tags` | `List[str]` | No | Arbitrary labels for filtering or routing tasks. |
| `dependencies` | `List[str]` | No | Other task identifiers that should be completed first. |

## Validation Rules

- `task_id`, `title`, and `summary` must be non-empty strings.
- Sequence fields (`context`, `acceptance_criteria`, `tags`, `dependencies`) automatically trim whitespace and reject blank or `None` entries.
- `priority` is optional but, when supplied, must be one of: `low`, `medium`, `high`, `critical`.
- `TaskSpec.has_acceptance_criteria()` returns `True` when at least one acceptance criterion is present, allowing the orchestrator to verify scope quickly.

## JSON Example

```json
{
  "task_id": "planning/task-loader",
  "title": "Implement backlog loader",
  "summary": "Read TaskSpec definitions from disk and expose them to the orchestrator.",
  "details": "Load structured task files and return immutable TaskSpec instances.",
  "context": [
    "docs/backlog.md",
    "docs/task_spec.md"
  ],
  "acceptance_criteria": [
    "Loader yields TaskSpec objects for each enabled task definition.",
    "Invalid or missing files are surfaced with actionable errors."
  ],
  "priority": "high",
  "tags": [
    "orchestration",
    "planning"
  ],
  "dependencies": []
}
```

## Integration Notes

- Use `TaskSpec.from_dict()` when reading task definitions from JSON or YAML sources; it validates required fields and normalises whitespace.
- Use `TaskSpec.to_dict()` to serialise instances for storage, logging, or model prompts.
- The backlog loader (see `docs/backlog.md`) should emit sequences of `TaskSpec` objects so downstream orchestration logic can reason about priorities and dependencies.

## Loading Task Specifications

Task definitions can be persisted as `.json` files inside a dedicated directory (e.g., `tasks/`). The helper `agent.core.task_loader.load_task_specs()` scans the directory recursively, ignoring hidden files and directories, and accepts three JSON layouts:

1. A single task object per file.
2. An array of task objects.
3. An object containing a top-level `tasks` array.

Each entry is validated via `TaskSpec.from_dict()`, and duplicate `task_id` values are rejected with a `TaskSpecLoadingError` that points to the conflicting file. This loader forms the foundation for replacing the orchestrator's placeholder fallback with backlog-driven execution.

## Repository Task Catalogue

A sample catalogue of high-priority tasks now lives in `tasks/active.json`. These TaskSpec entries mirror the top items in `docs/backlog.md`, providing concrete fixtures for tests and future orchestrator runs. Update or extend the catalogue as priorities shift so automated flows always have actionable work to select.

## Follow-Up

- Extend the schema with execution hints (e.g., default target paths or suggested quality gates) as the backlog loader evolves.
- Capture how task lifecycle state (ready/in progress/done) should be represented once persistence requirements are defined.
