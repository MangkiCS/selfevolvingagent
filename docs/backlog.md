# Automation Agent Backlog

_Status key:_ `[ ]` open, `[~]` in progress, `[x]` done.

## Ready Next (High Priority)
- [x] Audit `agent/orchestrator.py` to document the current execution flow, key entry points, and how prompts are loaded. Capture findings in `docs/orchestrator_overview.md`.
- [ ] Replace the `add_example_code()` fallback with logic that selects meaningful tasks from the backlog before editing files.
- [ ] Define a `TaskSpec` data model (e.g., in `agent/core/taskspec.py`) that captures requested changes, context, and acceptance criteria, alongside unit tests.

## Near Term
- [ ] Implement a lightweight backlog loader that reads structured tasks (YAML/JSON) and exposes them to the orchestrator.
- [ ] Create telemetry/logging utilities so orchestration steps emit structured logs.
- [ ] Add integration tests that exercise the orchestrator end-to-end on a sample task without touching production files.

## Discovery / Research
- [ ] Investigate how to persist state across runs (e.g., via JSON/YAML under `state/` or git notes) without relying on external services.
- [ ] Explore requirements for integrating with external issue trackers or PR platforms; identify data the orchestrator must accept.
- [ ] Determine minimal credential and configuration needs for interacting with remote APIs, to request from operators later.

## Future Opportunities
- [ ] Build a planning module that decomposes large tasks into ordered steps and tracks completion status.
- [ ] Introduce policy checks (security, license scanning) as part of the quality gate.
- [ ] Design a plugin system for domain-specific automation skills.

_Update this backlog every run: promote completed items, add discoveries, and re-prioritise as the agent evolves._
