# Orchestrator Overview

## Purpose
`agent/orchestrator.py` drives the automation workflow by preparing feature branches, invoking the language model with repository context, applying code patches, and publishing pull requests.

## Execution Flow (current MVP)

1. **Git Identity & Branching**
   - `ensure_git_identity()` configures the default Git author if missing.
   - `create_branch()` creates a new branch prefixed with `auto/` using the current UTC timestamp.

2. **Repository Snapshot**
   - `build_repo_snapshot()` collects up to 40 files from `agent/`, `tests/`, and `docs/`, skipping large/binary artefacts and truncating each file to 4000 bytes.
   - The snapshot is embedded in the LLM prompt so the model can reason about the repository without fetching everything.

3. **Prompt & Code Application**
   - The orchestrator loads system and task prompts from `agent/prompts/` and augments them with TaskSpec context produced by `agent.core.task_context.load_task_prompt()`.
   - Helper `write()` persists any returned `code_patches` or `new_tests` by overwriting the target files atomically.
   - When the model does not return actionable edits, the run records a warning event and exits without modifying the repository.

4. **Checks & PR Automation**
   - Local quality gates are currently disabled; `run_local_checks()` simply records that they were skipped.
   - Successful runs commit all modifications, push the `auto/` branch, and open a pull request labelled `auto`.
   - Failures from subprocesses, GitHub API calls, or LLM interactions are appended to `docs/run_events.json` so future runs (and the prompt snapshot) can inspect the most recent diagnostics.

## Gaps & Risks
- **Backlog state drift:** Completed TaskSpecs are not yet persisted automatically, so ready lists may include already-delivered work until the state store is updated.
- **Event log retention:** Persistent logging now exists under `docs/run_events.json`, but only the most recent 200 entries are stored and the format may need to evolve as telemetry requirements grow.
- **Snapshot limits:** Hard-coded file caps may hide critical context once the codebase grows; a smarter selection strategy is needed.

## Opportunities & Next Steps
- Persist completion of TaskSpecs as runs finish so future prompts can skip already delivered tasks.
- Expand telemetry to capture why a run exited early (e.g., no ready tasks) and surface that in operator dashboards.
- Capture run history, decisions, and troubleshooting notes under `docs/` to preserve institutional knowledge.
- Introduce structured logging/telemetry so orchestration steps are traceable.

## Open Questions
- What is the minimal persistent store we need for task state between runs (e.g., JSON under `state/` vs. Git notes)?
- How should the orchestrator prioritise multiple pending tasks when more than one is available?
- Which additional quality or security gates (e.g., dependency scanning) should be integrated as capabilities mature?

Refer to `docs/ROADMAP.md` and `docs/backlog.md` for the active implementation plan.
