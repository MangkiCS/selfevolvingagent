# Orchestrator Overview

## Purpose
`agent/orchestrator.py` drives the automation workflow by preparing feature branches, invoking the language model with repository context, applying code patches, running quality gates, and publishing pull requests.

## Execution Flow (current MVP)

1. **Git Identity & Branching**
   - `ensure_git_identity()` configures the default Git author if missing.
   - `create_branch()` creates a new branch prefixed with `auto/` using the current UTC timestamp.

2. **Repository Snapshot**
   - `build_repo_snapshot()` collects up to 40 files from `agent/`, `tests/`, and `docs/`, skipping large/binary artefacts and truncating each file to 4000 bytes.
   - The snapshot is embedded in the LLM prompt so the model can reason about the repository without fetching everything.

3. **Prompt & Code Application**
   - The orchestrator loads system and task prompts from `agent/prompts/` and sends them to the code model along with the snapshot.
   - Helper `write()` persists any returned `code_patches` or `new_tests` by overwriting the target files atomically.
   - When the model does not return targeted edits, `add_example_code()` overwrites `agent/core/hello.py`, `agent/core/buildinfo.py`, and `tests/test_hello.py` to keep the pipeline active—this placeholder must be retired.

4. **Quality Gates & PR Automation**
   - After applying changes, the orchestrator runs `ruff`, `mypy`, `bandit`, and `pytest` with coverage enforcement.
   - Successful runs commit all modifications, push the `auto/` branch, and open a pull request labelled `auto`.
   - Failures from subprocesses, quality gates, GitHub API calls, or LLM interactions are appended to `docs/run_events.json` so future runs (and the prompt snapshot) can inspect the most recent diagnostics.

## Gaps & Risks
- **Placeholder fallback:** `add_example_code()` produces noisy commits with no business value.
- **No backlog/task integration:** There is currently no mechanism to ingest structured work items or persist state across runs.
- **Event log retention:** Persistent logging now exists under `docs/run_events.json`, but only the most recent 200 entries are stored and the format may need to evolve as telemetry requirements grow.
- **Snapshot limits:** Hard-coded file caps may hide critical context once the codebase grows; a smarter selection strategy is needed.

## Opportunities & Next Steps
- Design a structured task specification (e.g., `TaskSpec`) plus storage format that the orchestrator can load safely.
- Replace `add_example_code()` with logic that selects and executes backlog tasks in a controlled manner.
- Capture run history, decisions, and troubleshooting notes under `docs/` to preserve institutional knowledge.
- Introduce structured logging/telemetry so orchestration steps are traceable.

## Open Questions
- What is the minimal persistent store we need for task state between runs (e.g., JSON under `state/` vs. Git notes)?
- How should the orchestrator prioritise multiple pending tasks when more than one is available?
- Which additional quality or security gates (e.g., dependency scanning) should be integrated as capabilities mature?

Refer to `docs/ROADMAP.md` and `docs/backlog.md` for the active implementation plan.
