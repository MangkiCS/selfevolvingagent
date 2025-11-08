from __future__ import annotations

import pytest

import agent.orchestrator as orchestrator
from agent.core import pipeline
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
    monkeypatch.setattr(orchestrator, "_maybe_create_llm_client", lambda: object())
    monkeypatch.setattr(orchestrator, "create_branch", lambda: "auto/test-branch")
    monkeypatch.setattr(orchestrator, "build_repo_snapshot", lambda **_: "_snapshot_")
    monkeypatch.setattr(orchestrator, "run_context_summary", lambda *args, **kwargs: pipeline.ContextSummary(summary="summary"))
    monkeypatch.setattr(
        orchestrator,
        "run_retrieval_brief",
        lambda *args, **kwargs: pipeline.RetrievalBrief(
            brief="",
            selected_context_ids=[],
            focus_paths=list(spec.context),
            handoff_notes="",
            open_questions=[],
            retrieved_snippets=[],
        ),
    )
    monkeypatch.setattr(orchestrator, "refresh_vector_cache", lambda _store, *, touched_paths: list(touched_paths))
    monkeypatch.setattr(orchestrator, "_get_vector_store", lambda: object())

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

    def fake_call_code_model(system: str, user: str, *, client=None) -> dict:
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
    monkeypatch.setattr(orchestrator, "_maybe_create_llm_client", lambda: object())
    monkeypatch.setattr(orchestrator, "run_context_summary", lambda *args, **kwargs: pipeline.ContextSummary(summary="summary"))
    monkeypatch.setattr(
        orchestrator,
        "run_retrieval_brief",
        lambda *args, **kwargs: pipeline.RetrievalBrief(
            brief="",
            selected_context_ids=[],
            focus_paths=list(spec.context),
        ),
    )

    def fail_branch() -> str:
        raise AssertionError("create_branch should not be called when no plan is returned")

    monkeypatch.setattr(orchestrator, "create_branch", fail_branch)
    monkeypatch.setattr(orchestrator, "commit_all", lambda message: pytest.fail("commit_all should not run"))
    monkeypatch.setattr(orchestrator, "push_branch", lambda branch: pytest.fail("push_branch should not run"))
    monkeypatch.setattr(orchestrator, "create_pull_request", lambda *args, **kwargs: pytest.fail("create_pull_request should not run"))

    writes: list[tuple[str, str]] = []
    monkeypatch.setattr(orchestrator, "write", lambda path, content: writes.append((path, content)))

    monkeypatch.setattr(orchestrator, "call_code_model", lambda system, user, *, client=None: {})

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
    monkeypatch.setattr(orchestrator, "_maybe_create_llm_client", lambda: object())
    monkeypatch.setattr(orchestrator, "build_repo_snapshot", lambda **_: "snapshot")
    monkeypatch.setattr(orchestrator, "run_context_summary", lambda *args, **kwargs: pipeline.ContextSummary(summary="summary"))
    monkeypatch.setattr(
        orchestrator,
        "run_retrieval_brief",
        lambda *args, **kwargs: pipeline.RetrievalBrief(brief="", selected_context_ids=[], focus_paths=list(spec.context)),
    )
    monkeypatch.setattr(orchestrator, "refresh_vector_cache", lambda _store, *, touched_paths: list(touched_paths))
    monkeypatch.setattr(orchestrator, "_get_vector_store", lambda: object())

    recorded: list[list[dict[str, str]]] = []

    def fake_log_admin_requests(requests):
        recorded.append(list(requests))
        return {"details": {"requests": list(requests)}}

    monkeypatch.setattr(orchestrator, "log_admin_requests", fake_log_admin_requests)
    monkeypatch.setattr(
        orchestrator,
        "call_code_model",
        lambda system, user, *, client=None: {"admin_requests": [{"summary": "Need API key"}]},
    )

    result = orchestrator.main()
    assert result == 0
    assert recorded == [[{"summary": "Need API key"}]]


def test_record_fallback_run_appends_entries(monkeypatch, tmp_path):
    spec = TaskSpec(
        task_id="task/fallback",
        title="Fallback test",
        summary="Ensure fallback runs persist structured notes.",
        acceptance_criteria=("Record fallback reason",),
    )

    monkeypatch.setattr(orchestrator, "ROOT", tmp_path)

    reason_one = "First failure"
    touched = orchestrator._record_fallback_run(spec, reason=reason_one)
    assert touched == ["docs/runbook/fallback_log.md"]

    log_path = tmp_path / "docs" / "runbook" / "fallback_log.md"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "# Fallback Runs" in content
    assert reason_one in content
    assert content.count("## ") == 1

    reason_two = "Second failure"
    touched_again = orchestrator._record_fallback_run(spec, reason=reason_two)
    assert touched_again == ["docs/runbook/fallback_log.md"]
    updated = log_path.read_text(encoding="utf-8")
    assert updated.count("## ") == 2
    assert reason_two in updated


def test_main_records_fallback_when_llm_missing(monkeypatch):
    spec = TaskSpec(
        task_id="task/fallback",
        title="Fallback handling",
        summary="Ensure orchestrator commits when no LLM is available.",
        details="The run should capture the failure in docs/runbook/fallback_log.md.",
        priority="high",
    )

    task_prompt = _make_task_prompt(spec)

    monkeypatch.setattr(orchestrator, "load_available_tasks", lambda: [spec])
    monkeypatch.setattr(orchestrator, "load_task_prompt", lambda _dir=None: task_prompt)
    monkeypatch.setattr(orchestrator, "ensure_git_identity", lambda: None)
    monkeypatch.setattr(orchestrator, "_maybe_create_llm_client", lambda: None)
    monkeypatch.setattr(orchestrator, "_detect_llm_unavailability_reason", lambda: "No API key configured")
    monkeypatch.setattr(orchestrator, "_get_vector_store", lambda: object())

    fallback_calls: list[tuple[TaskSpec, str]] = []

    def fake_record(task: TaskSpec, *, reason: str) -> list[str]:
        fallback_calls.append((task, reason))
        return ["docs/runbook/fallback_log.md"]

    monkeypatch.setattr(orchestrator, "_record_fallback_run", fake_record)

    refreshed_paths: list[list[str]] = []
    monkeypatch.setattr(
        orchestrator,
        "refresh_vector_cache",
        lambda _store, *, touched_paths: refreshed_paths.append(list(touched_paths)) or list(touched_paths),
    )

    monkeypatch.setattr(orchestrator, "build_repo_snapshot", lambda **_: "snapshot")

    def fail_call_code_model(*_args, **_kwargs):
        raise AssertionError("should not call code model")

    monkeypatch.setattr(orchestrator, "call_code_model", fail_call_code_model)

    created_branches: list[str] = []
    monkeypatch.setattr(orchestrator, "create_branch", lambda: created_branches.append("auto/fallback-branch") or "auto/fallback-branch")

    commits: list[str] = []
    monkeypatch.setattr(orchestrator, "commit_all", lambda message: commits.append(message))

    pushes: list[str] = []
    monkeypatch.setattr(orchestrator, "push_branch", lambda branch: pushes.append(branch))

    prs: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        orchestrator,
        "create_pull_request",
        lambda branch, title, body: prs.append((branch, title, body)),
    )

    result = orchestrator.main()

    assert result == 0
    assert fallback_calls == [(spec, "No API key configured")]
    assert refreshed_paths == [["docs/runbook/fallback_log.md"]]
    assert created_branches == ["auto/fallback-branch"]
    assert commits == ["chore: record fallback for task/fallback"]
    assert pushes == ["auto/fallback-branch"]
    assert prs and prs[0][0] == "auto/fallback-branch"
    assert prs[0][1] == "Fallback: Fallback handling (auto)"
    assert "No API key configured" in prs[0][2]
    assert "docs/runbook/fallback_log.md" in prs[0][2]


def test_main_surfaces_stage_metadata_on_llm_failure(monkeypatch, capsys):
    spec = TaskSpec(
        task_id="task/failure",
        title="Handle failures",
        summary="Ensure orchestrator surfaces stage metadata when LLM calls fail.",
        priority="high",
    )

    task_prompt = _make_task_prompt(spec)

    monkeypatch.setattr(orchestrator, "load_available_tasks", lambda: [spec])
    monkeypatch.setattr(orchestrator, "load_task_prompt", lambda _dir=None: task_prompt)
    monkeypatch.setattr(orchestrator, "ensure_git_identity", lambda: None)
    monkeypatch.setattr(orchestrator, "_get_vector_store", lambda: None)
    monkeypatch.setattr(orchestrator, "_maybe_create_llm_client", lambda: object())
    monkeypatch.setattr(orchestrator, "run_context_summary", lambda *args, **kwargs: pipeline.ContextSummary(summary="summary"))
    monkeypatch.setattr(
        orchestrator,
        "run_retrieval_brief",
        lambda *args, **kwargs: pipeline.RetrievalBrief(brief="", selected_context_ids=[], focus_paths=list(spec.context)),
    )

    events: list[dict[str, object]] = []

    def fake_append_event(*, level, source, message, details=None):  # type: ignore[no-untyped-def]
        entry = {
            "level": level,
            "source": source,
            "message": message,
            "details": details or {},
        }
        events.append(entry)
        return entry

    monkeypatch.setattr(orchestrator, "append_event", fake_append_event)

    def raise_failure(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise pipeline.LLMCallError(
            stage="execution_plan",
            attempts=3,
            model="test-model",
            error=RuntimeError("boom"),
        )

    monkeypatch.setattr(orchestrator, "call_code_model", raise_failure)

    result = orchestrator.main()
    assert result == 1

    stderr = capsys.readouterr().err
    assert "execution_plan" in stderr
    assert "test-model" in stderr

    failure_events = [event for event in events if event["message"] == "LLM call failed"]
    assert failure_events, "expected orchestrator to record failure event"
    failure_details = failure_events[-1]["details"]
    assert failure_details["stage"] == "execution_plan"
    assert failure_details["attempts"] == 3
    assert failure_details["model"] == "test-model"
    assert failure_details["error_type"] == "RuntimeError"


def test_main_does_not_checkout_previous_branch_when_model_fails(monkeypatch):
    spec = TaskSpec(
        task_id="task/failure",
        title="Handle model failure",
        summary="Ensure orchestrator does not attempt to checkout previous branch when no branch exists.",
        priority="high",
    )

    task_prompt = _make_task_prompt(spec)

    monkeypatch.setattr(orchestrator, "load_available_tasks", lambda: [spec])
    monkeypatch.setattr(orchestrator, "load_task_prompt", lambda _dir=None: task_prompt)
    monkeypatch.setattr(orchestrator, "ensure_git_identity", lambda: None)
    monkeypatch.setattr(orchestrator, "build_repo_snapshot", lambda **_: "snapshot")
    monkeypatch.setattr(orchestrator, "_maybe_create_llm_client", lambda: object())
    monkeypatch.setattr(orchestrator, "run_context_summary", lambda *args, **kwargs: pipeline.ContextSummary(summary="summary"))
    monkeypatch.setattr(
        orchestrator,
        "run_retrieval_brief",
        lambda *args, **kwargs: pipeline.RetrievalBrief(brief="", selected_context_ids=[], focus_paths=list(spec.context)),
    )
    monkeypatch.setattr(orchestrator, "refresh_vector_cache", lambda _store, *, touched_paths: list(touched_paths))
    monkeypatch.setattr(orchestrator, "_get_vector_store", lambda: object())

    checkout_commands: list[list[str]] = []

    def fake_sh(args, check=True, cwd=orchestrator.ROOT):  # type: ignore[override]
        checkout_commands.append(list(args))
        return ""

    monkeypatch.setattr(orchestrator, "sh", fake_sh)

    def fail_call_code_model(*_args, **_kwargs):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(orchestrator, "call_code_model", fail_call_code_model)

    result = orchestrator.main()
    assert result == 1
    assert ["git", "checkout", "-"] not in checkout_commands
