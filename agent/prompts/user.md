# AutoDev Orchestrator – Activation Brief

## Mission
Transform this repository into a practical, end-to-end software automation agent that can accept real feature requests, plan the necessary work, implement the changes, and deliver production-quality pull requests without manual babysitting.

Your priority on every invocation is to push the system closer to that goal through deliberate analysis, planning, and implementation.

## Current Context
- `agent/orchestrator.py` drives the workflow: it creates an `auto/` branch, prepares prompts, optionally calls this model, runs `ruff`, `mypy`, `bandit`, and `pytest`, then opens a PR.
- A placeholder fallback (`add_example_code()`) still rewrites `agent/core/hello.py`, `agent/core/buildinfo.py`, and `tests/test_hello.py`, generating meaningless churn.
- Prompts live in `agent/prompts/system.md` (German system message) and this file (user instructions).
- Package scaffolding exists under `agent/`, with basic smoke tests in `tests/`.

Assume no additional hidden context is provided unless you add it to the repository yourself.

## Short-Term Objectives
1. **Understand & Document the Baseline**
   - Inspect `agent/orchestrator.py` and related modules to capture current capabilities, limitations, and control flow.
   - Create or update `docs/roadmap.md` (or an equivalent document) summarising architecture, gaps, and next steps. Keep it current.

2. **Eliminate the No-Op Fallback**
   - Redesign or remove `add_example_code()` so the orchestrator only commits meaningful work.
   - Introduce mechanisms (e.g., a task queue, backlog file, or request parser) that surface real tasks for the agent to execute.

3. **Lay the Foundations for Real Automation**
   - Define how feature requests will be represented (e.g., structured specs, backlog files) and consumed by the agent.
   - Identify missing tooling (state management, evaluation harnesses, integrations) and prioritise implementing them.

4. **Adopt an Iterative Delivery Cycle**
   - For each run, choose the highest-leverage improvement, ensure tests cover the change, and update the roadmap/status notes.

## Workflow Expectations (Each Invocation)
1. **Sync Context**: Read relevant code, docs, and the roadmap. Summarise what changed since the last iteration if necessary.
2. **Update Planning Artefacts**: Keep `docs/roadmap.md` (or similar) in sync with discoveries, decisions, and upcoming tasks.
3. **Select a Concrete Goal**: Pick the most impactful next step that moves the agent toward autonomous usefulness.
4. **Design Before Coding**: Sketch architecture, data flows, and edge cases. Prefer incremental, testable units of work.
5. **Implement & Validate**: Modify code and tests together. Ensure `ruff`, `mypy`, `bandit`, and `pytest` will pass before handing work back to the orchestrator.
6. **Communicate Clearly**: In your final JSON response, include reasoning, the changes made, remaining risks, and suggestions for follow-up runs.

## Deliverable Standards
- Group related changes into cohesive patches; avoid drive-by edits.
- Tests are mandatory for new behaviour or bug fixes.
- Prefer explicit interfaces, type annotations, and docstrings that aid maintainability.
- When external data, credentials, or infrastructure are required, add a descriptive entry to `admin_requests` explaining the need and intended use.

## Guardrails & Quality
- Do not reintroduce the trivial "hello world" fallback.
- Preserve git history semantics expected by the orchestrator (branch naming, commit pipeline).
- Flag uncertainties, assumptions, or investigation needs in your notes/backlog.
- If you cannot make meaningful progress in one run, leave a detailed plan enabling the next iteration to continue seamlessly.

## Success Criteria
A successful future run should deliver tangible infrastructure or behavioural improvements (e.g., backlog ingestion, planning utilities, execution modules) that bring the system closer to autonomously satisfying real feature requests.

Own the outcome: each iteration must leave the repository and roadmap in a strictly better, more capable state than before.
