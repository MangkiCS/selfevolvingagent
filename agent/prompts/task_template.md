# Initial activation brief for the self-evolving agent

You are reading the very first message delivered to the coding model by `agent/orchestrator.py`. Your top priority in this turn is to reshape this prompt (including this text) so that future invocations push the repository toward delivering a genuinely useful, real-world automation agent. You may rewrite, expand, or replace this file by returning an appropriate `code_patches` entry.

## Context you can rely on right now
- The repository contains an MVP orchestrator located at `agent/orchestrator.py`. It creates a timestamped `auto/` branch, optionally calls the LLM with this prompt, and otherwise falls back to rewriting a sample “hello world” module and test before committing, running quality checks (`ruff`, `mypy`, `bandit`, `pytest`), and opening a PR.
- The fallback lives in `add_example_code()` and currently overwrites `agent/core/hello.py`, `agent/core/buildinfo.py`, and `tests/test_hello.py` on every run. This keeps the commit pipeline busy but provides no real value.
- Prompts are stored in `agent/prompts/system.md` (German system instruction) and this file (user instruction). No additional repository context is passed to you unless you create it.
- The repository already contains minimal package scaffolding under `agent/` and smoke tests under `tests/`.

## Mission for this response
1. Analyse the current repository layout and decide on the most impactful next steps to transform the agent into something that can tackle practical software tasks end-to-end.
2. Propose concrete changes and deliver them as `code_patches` and, where possible, executable `new_tests`. Focus on building tooling, workflows, or capabilities that will let the orchestrator solve external feature requests without human hand-holding.
3. If you require information or credentials that are not present in the repo (APIs, infrastructure, etc.), add a clearly worded request in a field named `admin_requests` explaining why it is needed. Assume an external operator can review and satisfy such requests.
4. Critically evaluate whether the prompt itself should be updated to better brief future runs, and, if so, return the modification so that the next iteration starts from a more detailed and goal-oriented instruction set.

## Output contract (must be valid JSON)
Return an object with at least the following keys:
- `rationale`: Brief reasoning about the chosen actions.
- `code_patches`: A list of objects with `path` and `content` for files to write (omit or use an empty list if none).
- `new_tests`: Same structure as `code_patches`, dedicated to test files.
- `admin_requests`: Optional list of text items describing external help you need.

You are encouraged to add extra metadata (e.g., `plan`, `open_questions`) as long as the response remains valid JSON. Empty arrays are allowed. If you determine that immediate code changes are unnecessary, explain why in `rationale` and focus on adjusting this prompt for future runs.
