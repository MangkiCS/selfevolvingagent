# Automation Agent Backlog

_Status key:_ `[ ]` open, `[~]` in progress, `[x]` done.

## Ready Next (High Priority)
- [x] Audit `agent/orchestrator.py` to document the current execution flow, key entry points, and how prompts are loaded. Capture findings in `docs/orchestrator_overview.md`.
- [x] Replace the `add_example_code()` fallback with logic that selects meaningful tasks from the backlog before editing files.
- [x] Define a `TaskSpec` data model (e.g., in `agent/core/taskspec.py`) that captures requested changes, context, and acceptance criteria, alongside unit tests.
- [x] Integrate the file-backed `TaskSpec` loader into `agent/orchestrator.py`, replacing the placeholder fallback.
  - The orchestrator now loads backlog context via `load_task_prompt()` and injects ready-task details into the model prompt.
  - Runs skip execution when no ready tasks exist, emitting events instead of mutating the repository with placeholder content.
  - Commit and PR metadata reuse the selected TaskSpec title so automation outputs align with the backlog terminology.
  - Next: persist task completion state automatically once changes land to keep the backlog in sync.

## Near Term
- [x] Implement a lightweight backlog loader that reads structured tasks (JSON) and exposes them to the orchestrator (see `agent/core/task_loader.py`).
- [x] Introduce task selection helpers to prioritise TaskSpec items and format prompt summaries for the orchestrator.
- [ ] Create telemetry/logging utilities so orchestration steps emit structured logs.
- [ ] Add integration tests that exercise the orchestrator end-to-end on a sample task without touching production files.
- [ ] Extend `TaskSpec` with execution hints (e.g., default target paths, suggested quality checks) once the loader is available.
- [x] Persist example task definitions under a repository directory to validate the loader in an end-to-end flow.
  - Sample catalogue maintained at `tasks/active.json`; keep it aligned with the high-priority backlog.
- [~] Wire the `CompletedTaskStore` into the orchestration loop so completed tasks are skipped automatically.
  - `load_task_batch()` and `load_task_prompt()` now read completed identifiers from the persisted state file by default, reducing boilerplate for the orchestrator.
  - Next: have the orchestrator update the store as tasks complete and automatically skip work that is already marked done.

## Discovery / Research
- [~] Investigate how to persist state across runs (baseline `CompletedTaskStore` implemented in `agent/core/task_state.py`; follow-up to expand persisted metadata and reconcile concurrent runs).
- [ ] Explore requirements for integrating with external issue trackers or PR platforms; identify data the orchestrator must accept.
- [ ] Determine minimal credential and configuration needs for interacting with remote APIs, to request from operators later.

## Future Opportunities
- [ ] Build a planning module that decomposes large tasks into ordered steps and tracks completion status.
- [ ] Introduce policy checks (security, license scanning) as part of the quality gate.
- [ ] Design a plugin system for domain-specific automation skills.

_Update this backlog every run: promote completed items, add discoveries, and re-prioritise as the agent evolves._
