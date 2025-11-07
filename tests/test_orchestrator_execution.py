from __future__ import annotations

import pytest

import agent.orchestrator as orchestrator
from agent.core.task_context import TaskBatch, TaskPrompt
from agent.core.taskspec import TaskSpec


@pytest.fixture(autouse=True)
def isolate_task_catalog():
    original = dict(orchestrator._TASK_CATALOG)
    orchestrator._TASK_CATALOG.clear()
    try:
        yield
    finally:
        orchestrator._TASK_CATALOG.clear()
        orchestrator._TASK_CATALOG.update(original)


def _make_task_prompt(*ready_specs: TaskSpec) -> TaskPrompt:
    batch = TaskBatch(ready=tuple(ready_specs), blocked=(), completed=())
    return TaskPrompt(batch=batch, prompt="Ready tasks available.")


def test_select_task_for_execution_prefers_higher_priority():
    low = TaskSpec(
        task_id="task/low",
        title="Low priority",
        summary="Low priority work",
        priority="low",
    )
    critical = TaskSpec(
        task_id="task/critical",
        title="Critical priority",
        summary="Critical work",
        priority="critical",
    )

    orchestrator._TASK_CATALOG[low.task_id] = low
    orchestrator._TASK_CATALOG[critical.task_id] = critical

    task_prompt = _make_task_prompt(low, critical)

    selected = orchestrator._select_task_for_execution(task_prompt)
    assert selected is not None
    assert selected.task_id == critical.task_id


def test_format_selected_task_section_includes_key_fields():
    spec = TaskSpec(
        task_id="task/demo",
        title="Demo",
        summary="Demonstrate formatting",
        details="Explain how the orchestrator should treat the selected task.",
        context=("docs/backlog.md", "docs/ROADMAP.md"),
        acceptance_criteria=("No placeholder files",),
        priority="high",
        tags=("execution",),
        dependencies=("task/base",),
    )

    section = orchestrator._format_selected_task_section(spec)

    assert "### Task ID: task/demo" in section
    assert "**Title:** Demo" in section
    assert "**Priority:** high" in section
    assert "No placeholder files" in section
    assert "Dependencies" in section
    assert "docs/backlog.md" in section


def test_main_executes_task_without_placeholder_artifacts(monkeypatch):
    spec = TaskSpec(
        task_id="task/execute",
        title="Execute orchestrated task",
        summary="Ensure orchestrator dispatches TaskSpec instructions.",
        details="Use the TaskSpec content to guide execution instead of fallbacks.",
        context=("docs/backlog.md",),
        acceptance_criteria=("Do not touch sample placeholder modules.",),
        priority="high",
        tags=("orchestration",),
    )

    task_prompt = _make_task_prompt(spec)

    def fake_load_available_tasks():
        orchestrator._TASK_CATALOG.clear()
        orchestrator._TASK_CATALOG[spec.task_id] = spec
        return [spec]

    monkeypatch.setattr(orchestrator, "load_available_tasks", fake_load_available_tasks)
    monkeypatch.setattr(orchestrator, "load_task_prompt", lambda _dir=None: task_prompt)
    monkeypatch.setattr(orchestrator, "ensure_git_identity", lambda: None)
    monkeypatch.setattr(orchestrator, "create_branch", lambda: "auto/test-branch")
    monkeypatch.setattr(orchestrator, "build_repo_snapshot", lambda **_: "_snapshot_")

    writes: list[tuple[str, str]] = []
    monkeypatch.setattr(orchestrator, "write", lambda path, content: writes.append((path, content)))

    commits: list[str] = []
    monkeypatch.setattr(orchestrator, "commit_all", lambda message: commits.append(message))
    monkeypatch.setattr(orchestrator, "push_branch", lambda branch: None)

    prs: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        orchestrator,
        "create_pull_request",
        lambda branch, title, body: prs.append((branch, title, body)),
    )

    def fake_call_code_model(system: str, user: str) -> dict:
        assert "## Selected Task for Execution" in user
        assert spec.summary in user
        return {
            "code_patches": [
                {"path": "docs/progress.md", "content": "# Progress\nUpdated\n"}
            ],
            "new_tests": [],
        }

    monkeypatch.setattr(orchestrator, "call_code_model", fake_call_code_model)

    result = orchestrator.main()
    assert result == 0

    assert writes == [("docs/progress.md", "# Progress\nUpdated\n")]
    placeholder_paths = {"agent/core/hello.py", "docs/buildinfo.md", "tests/test_hello.py"}
    assert not any(path in placeholder_paths for path, _ in writes)

    assert commits == ["feat: Execute orchestrated task"]
    assert prs and prs[0][1] == "Execute orchestrated task (auto)"
    assert prs[0][2] == spec.summary


def test_main_skips_when_model_returns_no_plan(monkeypatch):
    spec = TaskSpec(
        task_id="task/skip",
        title="Skip when no plan",
        summary="Orchestrator should not fall back to placeholder writes.",
        priority="high",
    )

    task_prompt = _make_task_prompt(spec)

    monkeypatch.setattr(orchestrator, "load_available_tasks", lambda: [spec])
    monkeypatch.setattr(orchestrator, "load_task_prompt", lambda _dir=None: task_prompt)
    monkeypatch.setattr(orchestrator, "ensure_git_identity", lambda: None)
    monkeypatch.setattr(orchestrator, "build_repo_snapshot", lambda **_: "_snapshot_")

    def fail_branch() -> str:
        raise AssertionError("create_branch should not be called when no plan is returned")

    monkeypatch.setattr(orchestrator, "create_branch", fail_branch)
    monkeypatch.setattr(orchestrator, "commit_all", lambda message: pytest.fail("commit_all should not run"))
    monkeypatch.setattr(orchestrator, "push_branch", lambda branch: pytest.fail("push_branch should not run"))
    monkeypatch.setattr(orchestrator, "create_pull_request", lambda *args, **kwargs: pytest.fail("create_pull_request should not run"))

    writes: list[tuple[str, str]] = []
    monkeypatch.setattr(orchestrator, "write", lambda path, content: writes.append((path, content)))

    monkeypatch.setattr(orchestrator, "call_code_model", lambda system, user: {})

    result = orchestrator.main()
    assert result == 0
    assert writes == []


def test_admin_requests_are_logged_and_announced(monkeypatch, capsys):
    spec = TaskSpec(
        task_id="task/admin",
        title="Surface admin requests",
        summary="Ensure admin requests reach the event log and stdout.",
        priority="high",
    )

    task_prompt = _make_task_prompt(spec)

    monkeypatch.setattr(orchestrator, "load_available_tasks", lambda: [spec])
    monkeypatch.setattr(orchestrator, "load_task_prompt", lambda _dir=None: task_prompt)
    monkeypatch.setattr(orchestrator, "ensure_git_identity", lambda: None)
    monkeypatch.setattr(orchestrator, "build_repo_snapshot", lambda **_: "snapshot")

    recorded: list[list[dict[str, str]]] = []

    def fake_log_admin_requests(requests):
        recorded.append(list(requests))
        return {"details": {"requests": list(requests)}}

    monkeypatch.setattr(orchestrator, "log_admin_requests", fake_log_admin_requests)
    monkeypatch.setattr(orchestrator, "call_code_model", lambda system, user: {"admin_requests": [{"summary": "Need API key"}]})

    result = orchestrator.main()
    assert result == 0
    assert recorded == [[{"summary": "Need API key"}]]

    stdout = capsys.readouterr().out
    assert "Admin assistance requested" in stdout
    assert "Need API key" in stdout
