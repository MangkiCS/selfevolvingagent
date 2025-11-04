# Mission Brief: Build a Self-Sufficient Automation Agent

## Repository Snapshot
- `agent/orchestrator.py` orchestrates each run, creates timestamped `auto/` branches, and currently falls back to rewriting toy modules before committing, running `ruff`, `mypy`, `bandit`, and `pytest`, then opening a PR.
- `agent/core/hello.py`, `agent/core/buildinfo.py`, and `tests/test_hello.py` are overwritten by the fallback logic and provide no lasting value.
- Prompts live in `agent/prompts/system.md` (German system message) and this file (user brief). No other context is injected automatically.
- The package structure under `agent/` plus smoke tests under `tests/` form the current scaffold.

## Strategic Objectives
1. Replace the placeholder fallback with workflows that push the repository toward a production-ready automation agent capable of solving external software tasks end-to-end.
2. Establish persistent planning artifacts (e.g., backlog, state files, design docs) so progress compounds across runs.
3. Build modular capabilities for task intake, prioritisation, execution, verification, and reporting.
4. Maintain high engineering standards: typed Python, clean architecture, comprehensive tests, documentation, and automated quality gates.

## Default Workflow for Each Run
1. **Assess Context**
   - Inspect repository changes since the last run and review any planning/state artifacts.
   - Update or create a succinct changelog or state file (e.g., `STATE.md`) summarising insights and next steps.

2. **Plan Deliberately**
   - Maintain or extend a living roadmap/backlog (e.g., `docs/backlog.md`) with prioritised, actionable tasks.
   - Select the highest-impact item that can be advanced meaningfully in the current run.
   - Outline a step-by-step plan before touching code; ensure the plan includes testing and validation.

3. **Execute with Rigor**
   - Write production-quality code with clear abstractions and docstrings.
   - Introduce or update automated tests alongside new functionality.
   - Prefer incremental, reversible changes that keep the repository in a releasable state.
   - When refactoring, preserve behaviour and expand test coverage to lock in improvements.

4. **Validate**
   - Run the full quality suite (`ruff`, `mypy`, `bandit`, `pytest`) locally or via CI assumptions.
   - Address all failures before finishing. If blocked, document precisely why and propose remediation.

5. **Record Outcomes**
   - Update planning/state artifacts with accomplished work, outstanding issues, and recommended next steps.
   - Summarise design decisions and testing results in commit/PR context when applicable.

## Deliverables & Conventions
- Always provide `code_patches` with complete file contents and pair them with corresponding `new_tests` when functionality changes.
- Ensure new features are covered by tests; prefer `pytest` style and organise fixtures/helpers for reuse.
- Keep documentation in sync (README, `docs/`, inline docstrings, changelogs).
- When external resources (APIs, credentials, infra) are required, add precise entries to `admin_requests` explaining the need and intended usage.

## Immediate Priorities
1. Design and implement a meaningful fallback/task execution pipeline that advances the roadmap instead of rewriting sample code.
2. Introduce persistent storage for agent state, backlog, and decision logs.
3. Harden the orchestrator: clearer logging, error handling, configurable prompts, and guardrails for multi-step workflows.
4. Expand tests to cover orchestrator behaviour, planning utilities, and any new modules.

## Collaboration Principles
- Be explicit about assumptions and call out uncertainties or missing information.
- When blocked, downgrade gracefully by improving documentation/tests rather than reintroducing toy artefacts.
- Favour small, composable utilities over monoliths; design for extensibility.
- Treat security, privacy, and reliability as first-class concerns.

## When to Update this Brief
- If the strategic direction changes materially, revise this prompt to keep future runs aligned with the latest mission and context.
- Document major revisions in the state/backlog artifacts so the evolution of the brief remains traceable.
