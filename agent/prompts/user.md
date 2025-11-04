# Activation brief for the self-evolving automation agent

## Strategic Mission
Transform this repository from a placeholder orchestrator into a production-grade automation agent that can ingest real feature requests, plan implementation work, deliver code, and validate the results end-to-end.

## Known Starting Context
- Entry point: `agent/orchestrator.py` creates a timestamped `auto/` branch, orchestrates calls into this prompt, runs quality gates (`ruff`, `mypy`, `bandit`, `pytest`), and opens a PR.
- Current fallback (`add_example_code`) overwrites `agent/core/hello.py`, `agent/core/buildinfo.py`, and `tests/test_hello.py` with demo content on every run.
- System prompt: `agent/prompts/system.md` (German). This file supplies the user prompt. No other context is injected unless you create it.

## Immediate Objectives for Upcoming Runs
1. **Baseline Analysis & Documentation**
   - Inspect the repository structure and document the current orchestrator behavior, tooling, and limitations.
   - Produce a concise architecture summary (consider `docs/architecture.md` or similar) and capture outstanding gaps.
   - Verify the CI/quality checks pipeline locally (`ruff`, `mypy`, `bandit`, `pytest`) to understand constraints.

2. **Replace the Fallback with Value-Adding Behavior**
   - Design and implement a planning/execution workflow that interprets feature requests, generates implementation plans, updates code, and runs the quality gates.
   - Remove or gate the demo fallback so it no longer overwrites useful work.
   - Introduce state/configuration that allows the orchestrator to manage work units (e.g. tasks queued via files, CLI args, or issue ingestion).

3. **Build Core Capabilities**
   - Add utilities for repository introspection (dependency graph, file summaries) to help future reasoning.
   - Establish a durable memory/log of past actions (e.g. under `agent/logs/` or `docs/history/`).
   - Create scaffold tests that exercise the new workflow end-to-end.
   - Ensure developer ergonomics: lint config, type hints, documentation, and examples for running the agent manually.

## Operating Guidelines for Each Iteration
- Produce a clear plan before implementation. Explicitly call out assumptions, risks, and validation strategy.
- Favor incremental, reversible changes with strong tests. Keep diffs focused.
- Whenever modifying orchestration logic, update accompanying docs/tests so the new behavior is observable and verifiable.
- Prefer Python 3.11+ standard library and existing dependencies. Seek admin support before adding external services/secrets.
- If information, credentials, or infrastructure are missing, populate the `admin_requests` field with a concise justification.

## Quality & Validation Expectations
- Follow TDD/BDD principles where feasible: add failing tests, implement, then confirm green.
- Ensure `ruff`, `mypy`, `bandit`, and `pytest` pass locally before concluding an iteration.
- Document significant architectural decisions (ADR-style) when behavior or design changes meaningfully.

## Fallback & Escalation Clause
- Do **not** rely on or reinstate the legacy "hello world" fallback. If blocked or uncertain, surface the issue via rationale and/or `admin_requests` rather than committing placeholder changes.

## Collaboration Notes
- Maintain a running backlog or roadmap (e.g., `docs/roadmap.md`) identifying upcoming milestones.
- Keep PRs and commit messages informative, referencing the plan executed.

Stay outcome-focused: each run should measurably advance the agent toward autonomous, practical software delivery.
