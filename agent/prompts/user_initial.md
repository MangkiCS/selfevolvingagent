# Self-Evolving Agent Kickoff (v3)

## Current Context
- The repository contains an MVP automation orchestrator under `agent/orchestrator.py`.
- The orchestrator selects ready backlog items from TaskSpecs and skips execution when no actionable plan is returned.
- Automated quality gates are currently disabled; apply judgement when validating work.
- Documentation/backlog live under `docs/` and must be kept current.

## Long-Term Goal
Build an autonomous engineering agent that can accept structured feature requests, plan and implement changes, validate them, and open production-ready pull requests with minimal human oversight.

## Immediate Priorities
1. Document the existing orchestrator behaviour and identify extension seams.
2. Design and persist structured task specifications and a backlog ingestion flow.
3. Evolve the TaskSpec-driven execution loop to apply backlog tasks safely and record outcomes.
4. Establish documentation and decision records so future runs can operate with full context.

## Run Protocol
1. Review repository state, docs, and backlog (`docs/ROADMAP.md`, `docs/backlog.md`).
2. Summarise relevant context and choose concrete objectives for the run.
3. Record a plan with at least three steps before editing code.
4. Implement incrementally with tests, ensuring typing and linting are considered.
5. Update docs/backlog to reflect progress, open questions, and next steps.
6. Respond with JSON including `rationale`, `plan`, `code_patches`, `new_tests`, `admin_requests`.

## Guardrails
- Maintain high standards for typing, testing, security, and documentation.
- Avoid recreating placeholder churn; every change should advance autonomous execution.
- Use `admin_requests` to request credentials or information unavailable in-repo.

Keep each run focused on unlocking tangible capabilities that move the agent toward autonomous delivery.
