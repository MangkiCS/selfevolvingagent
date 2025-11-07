"""Tests for orchestrator task loading integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.core.task_context import TaskContextError
from agent.orchestrator import _TASK_CATALOG, load_available_tasks


def _write_task_file(path: Path, entries: list[dict[str, object]]) -> None:
    path.write_text(json.dumps(entries), encoding="utf-8")


def test_load_available_tasks_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    specs = [
        {
            "task_id": "example/task",
            "title": "Example task",
            "summary": "Demonstrate loading",
        }
    ]
    _write_task_file(tasks_dir / "sample.json", specs)

    monkeypatch.setattr("agent.orchestrator.DEFAULT_TASKS_DIR", tasks_dir)

    loaded = load_available_tasks()

    assert [spec.task_id for spec in loaded] == ["example/task"]
    assert _TASK_CATALOG["example/task"].summary == "Demonstrate loading"


def test_load_available_tasks_missing_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing_dir = tmp_path / "missing"
    monkeypatch.setattr("agent.orchestrator.DEFAULT_TASKS_DIR", missing_dir)

    with pytest.raises(TaskContextError) as excinfo:
        load_available_tasks()

    assert excinfo.value.path == missing_dir
    assert str(missing_dir) in str(excinfo.value)


def test_load_available_tasks_invalid_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    broken_path = tasks_dir / "broken.json"
    broken_path.write_text("{\n", encoding="utf-8")

    monkeypatch.setattr("agent.orchestrator.DEFAULT_TASKS_DIR", tasks_dir)

    with pytest.raises(TaskContextError) as excinfo:
        load_available_tasks()

    assert excinfo.value.path == broken_path
    assert str(broken_path) in str(excinfo.value)
