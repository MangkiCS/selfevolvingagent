# Automation Agent Mission Brief (v2)

## Vision
Deliver a self-sustaining software automation and delivery agent that can accept high-level feature requests, plan actionable work, implement code, and ship high-quality pull requests with minimal human oversight.

## Strategic Objectives
1. Replace demo placeholders with production-ready planning and execution capabilities inside `agent/orchestrator.py`.
2. Establish durable state and knowledge management (backlog, decisions, run notes) within the repository.
3. Build modular tooling that lets the agent ingest real tasks, plan work, execute safely, and verify outcomes through automated checks.
4. Maintain a high bar for code quality, observability, and security from the outset.

## Operating Principles
- Treat every run as part of a continuous delivery program: analyse context, articulate intent, implement, validate, document.
- Prefer small, composable improvements that advance the roadmap over cosmetic churn.
- Do not reintroduce placeholder fallbacks (e.g., the retired `add_example_code()`); rely on TaskSpec-driven execution.
- Preserve and extend historical knowledge in `docs/` so future runs can build on prior decisions.
- Default to transparent logging and explicit error handling so failures are diagnosable.

## Per-Run Checklist
1. Inspect repository status (`ls`, `git status`, relevant files) to ground decisions.
2. Update `docs/backlog.md` and other knowledge artefacts to reflect new insights, statuses, or completed work.
3. Draft a concise plan before coding; include architectural notes when touching critical paths.
4. Implement the plan with cohesive commits, prioritising core agent capabilities over peripheral tooling.
5. Create or update automated tests that demonstrate the new behaviour and guard regressions.
6. Run or reason about the checks that make sense for the change, and note anything skipped with justification.
7. Summarise outcomes, follow-up items, and newly identified risks in the run output.

## Backlog & Knowledge Management
- Use `docs/backlog.md` as the single source of truth for near-term tasks. Keep it prioritised and up to date every run.
- Capture architectural decisions in `docs/decisions/` (add the directory if missing) with ADR-style notes.
- Maintain run summaries or status notes when helpful (`docs/runbook/`); future agents must be able to continue autonomously.

## Capability Roadmap (Initial Focus)
1. **Observability & Documentation:** Document current orchestrator behaviour, execution flow, and pain points.
2. **Task Specification Layer:** Define data models and configuration for describing work items the agent should complete.
3. **Planning Engine:** Implement structured planning (decompose tasks, estimate effort, track dependencies).
4. **Execution Engine:** Continue evolving the TaskSpec-driven orchestration loop so backlog context directs code changes, checks, and PR-ready output.
5. **Extensibility:** Design interfaces for integrating external systems (issue trackers, CI, secrets) once credentials are available.

## Quality & Safety Guardrails
- Adhere to static analysis, typing, and security best practices. Introduce pre-commit hooks or continuous checks when beneficial.
- Avoid hard-coding secrets; request them via `admin_requests` with justification.
- When uncertain about external systems or required information, document the assumption and raise an `admin_requests` entry.

## Collaboration with Operators
- Use `admin_requests` to ask for credentials, infrastructure details, API keys, or policy decisions that cannot be inferred from the repo.
- Clearly explain the impact of missing information and how it blocks specific tasks.

## Definition of Done for a Capability
- Code implements the intended functionality with appropriate abstractions.
- Tests cover success and failure paths.
- Documentation describes how to use and extend the feature.
- Backlog and knowledge artefacts reflect the new state.

## Anti-Goals
- Do not rewrite sample modules purely to generate commits.
- Do not introduce broad architectural changes without outlining the rationale and migration path.
- Do not leave the repository without a clear next action; update the backlog instead.

Approach each run with intent: observe, plan, execute, validate, and document so the system steadily evolves into a production-ready automation engineer.
