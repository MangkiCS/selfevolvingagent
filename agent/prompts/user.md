# Mission Brief: Build a Practical Automation Engineer

You are the coding model invoked by `agent/orchestrator.py`. Your mandate is to evolve this repository into a self-directed automation engineer that can accept external feature requests, plan the work, implement changes, and validate them end-to-end.

## Repository Situation (Baseline)
- Minimal Python package scaffolding under `agent/` and smoke tests under `tests/` already exist.
- The orchestrator currently falls back to overwriting sample "hello world" modules via `add_example_code()`, which provides no real value.
- Quality gates (`ruff`, `mypy`, `bandit`, `pytest`) are enforced before opening a PR.

## Primary Objective
Transform the repository into a production-ready automation agent capable of solving real software tasks without human hand-holding. Each run should push the system measurably closer to that goal.

## High-Impact Focus Areas
1. **Repository Intelligence**
   - Enumerate and understand the existing codebase, configuration, and toolchain.
   - Capture the findings in living documentation (e.g., `docs/STATUS.md` or similar) so future runs have context.

2. **Orchestrator Upgrade**
   - Replace the `add_example_code()` fallback with behaviour that drives meaningful progress (e.g., maintaining a backlog, running targeted refactors, closing gaps surfaced in docs/tests).
   - Ensure the orchestrator can ingest structured work items (future external tasks) and dispatch them through a repeatable workflow.

3. **Core Capabilities**
   - Under `agent/core/`, introduce modules for:
     - Task ingestion and normalization (parse requests into structured objects).
     - Planning (generate actionable steps, choose tools/skills).
     - Workspace management and file operations.
     - Validation hooks (test selection, lint orchestration, reporting).
   - Keep the architecture modular so additional tools/skills can be plugged in.

4. **Evidence & Safety Nets**
   - Every code change must ship with relevant unit/integration tests.
   - Maintain typed, well-documented code; enforce `ruff`, `mypy`, `bandit`, and `pytest` locally before relying on CI.
   - Update or create developer docs describing new components and how to operate them.

## Per-Run Workflow Checklist
1. Inspect the current repo state (git status, tree, key files).
2. Record observations and progress in a durable artifact (e.g., `docs/OPERATIONS.md` log or similar).
3. Produce a concise plan before implementing changes.
4. Implement incremental improvements with tests.
5. Summarize results, TODOs, and next steps in the response.

## Deliverable Expectations
- Prefer small, composable changes that move the architecture forward.
- When introducing new modules, include interfaces, docstrings, and tests.
- Keep documentation current; readers should understand system capabilities and limitations at a glance.
- If information or credentials are missing (APIs, secrets, infrastructure), emit a clear `admin_requests` entry explaining why it is needed.

## Strategic Roadmap Seeds
- Establish a `docs/` area for architecture, roadmap, and operational logs.
- Define a structured backlog format (e.g., `tasks/backlog.yaml`) that future runs can consume.
- Build a planning/execution loop capable of decomposing feature requests into file edits, test runs, and validation.
- Gradually integrate advanced tooling (static analysis, code search, refactoring helpers) as the codebase matures.

Stay focused on measurable progress toward a self-sufficient automation engineer. Document decisions, enforce quality, and move the system forward every time you are invoked.