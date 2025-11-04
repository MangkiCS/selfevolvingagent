# Roadmap

_Status legend: [ ] TODO • [/] In Progress • [x] Done_

This document is maintained by the agent. Update statuses, add discoveries, and record follow-up items after every meaningful change.

## Milestone 1 — Stabilize the orchestrator foundation
- [ ] Document the current `agent/orchestrator.py` control flow and module responsibilities (target: `docs/ARCHITECTURE.md`).
- [ ] Replace the `add_example_code()` fallback with a task/backlog-driven execution path that only touches intended files.
- [ ] Capture the developer workflow in `README.md` (how to trigger runs, quality gates, branching model).

## Milestone 2 — Backlog-driven execution
- [ ] Design and implement a persistent backlog format (e.g., `backlog.yaml`) that the orchestrator can read and update.
- [ ] Introduce a planning component that selects the next actionable task and passes focused prompts to the coding agent.
- [ ] Add safeguards to skip executions when no actionable backlog items exist, avoiding noop commits.

## Milestone 3 — External request fulfillment
- [ ] Support ingesting structured feature requests (files, templates, or API input) and mapping them to backlog tasks.
- [ ] Expand automated validation (integration tests, smoke environments) to increase confidence in generated changes.
- [ ] Provide tooling to summarize completed work and surface follow-up items in PR descriptions or changelogs.

## Open Questions
- How should external operators submit new work items (file drop, API, issue tracker)?
- What secrets or credentials will be required for integrations beyond the local checks?

## Recently Completed
- _Nothing yet — this is the baseline snapshot._
