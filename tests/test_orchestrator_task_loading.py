"""Tests for orchestrator task loading integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.core.task_context import TaskContextError
from agent.orchestrator import _TASK_CATALOG, load_available_tasks


def _write_task_file(path: Path, entries: list[dict[str, object]]) -> None:
    path.write_text(json.dumps(entries), encoding="utf-8")


def test_load_available_tasks_success(tmp_path: Path) -> None:
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

    loaded = load_available_tasks(tasks_dir)

    assert [spec.task_id for spec in loaded] == ["example/task"]
    assert _TASK_CATALOG["example/task"].summary == "Demonstrate loading"


def test_load_available_tasks_invalid_payload(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    (tasks_dir / "broken.json").write_text("{\n", encoding="utf-8")

    with pytest.raises(TaskContextError) as excinfo:
        load_available_tasks(tasks_dir)

    assert "Invalid JSON" in str(excinfo.value)
    assert str(tasks_dir / "broken.json") in str(excinfo.value)
