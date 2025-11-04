# Roadmap: Self-Evolving Automation Agent

## Purpose
Provide a living backlog that guides the transformation from the current MVP into a production-ready automation engineer capable of delivering real features autonomously.

## Phase 0 – Baseline Assessment
- Audit `agent/orchestrator.py` to understand branch creation, prompt loading, and fallback behaviour.
- Catalogue existing modules, tests, and tooling gaps.
- Document findings and architectural questions.

## Phase 1 – Replace the Placeholder Fallback
1. Specify the desired task intake mechanism (e.g., structured request files, API queue).
2. Refactor the orchestrator to read actionable work instead of rewriting sample modules.
3. Introduce configuration and state management needed to track task progress.
4. Add comprehensive tests (unit and integration) covering the new orchestration flow.

## Phase 2 – Execution Capabilities
- Build core automation primitives (code editing, diff planning, test running, reporting).
- Implement robust error handling, retries, and logging.
- Ensure security checks surface actionable feedback.

## Phase 3 – External Integrations
- Connect to real task sources (ticketing systems, Git providers) once credentials and APIs are available.
- Add notification/approval workflows as required by operators.

## Ongoing Engineering Practices
- Maintain high test coverage and static analysis hygiene appropriate for the stack.
- Record significant design choices in decision logs.
- Keep documentation current with each iteration.

## Immediate Next Steps
- [x] Document the current orchestrator control flow and identify seams for injecting real task handling (see `docs/orchestrator_overview.md`).
- [ ] Draft a design for a persistent task queue or request format to replace `add_example_code`.
- [ ] Begin implementing the new orchestration pathway with supporting tests.
