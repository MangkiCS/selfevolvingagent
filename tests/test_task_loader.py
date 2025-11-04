from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.core.task_loader import TaskSpecLoadingError, load_task_specs


def test_load_task_specs_from_directory(tmp_path: Path) -> None:
    tasks_root = tmp_path / "tasks"
    tasks_root.mkdir()

    (tasks_root / "main.json").write_text(
        json.dumps(
            [
                {
                    "task_id": "task-alpha",
                    "title": "Implement planning cache",
                    "summary": "Cache plan artefacts to avoid redundant computation.",
                    "priority": "medium",
                    "acceptance_criteria": [
                        "Plans are reused when unchanged inputs are provided."
                    ],
                },
                {
                    "task_id": "task-beta",
                    "title": "Surface task visibility",
                    "summary": "Expose task status via structured logging output.",
                    "priority": "low",
                },
            ]
        ),
        encoding="utf-8",
    )

    nested = tasks_root / "nested"
    nested.mkdir()
    (nested / "extra.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "task_id": "task-gamma",
                        "title": "Integrate loader into orchestrator",
                        "summary": "Wire the disk-backed loader into the orchestration flow.",
                        "priority": "High",
                        "dependencies": ["task-alpha"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    specs = load_task_specs(tasks_root)

    assert [spec.task_id for spec in specs] == ["task-alpha", "task-beta", "task-gamma"]
    assert specs[0].has_acceptance_criteria()
    assert specs[-1].priority == "high"


def test_load_task_specs_invalid_json(tmp_path: Path) -> None:
    tasks_root = tmp_path / "tasks"
    tasks_root.mkdir()
    (tasks_root / "broken.json").write_text("{ invalid json }", encoding="utf-8")

    with pytest.raises(TaskSpecLoadingError) as excinfo:
        load_task_specs(tasks_root)

    assert "Invalid JSON payload" in str(excinfo.value)


def test_load_task_specs_duplicate_task_ids(tmp_path: Path) -> None:
    tasks_root = tmp_path / "tasks"
    tasks_root.mkdir()

    (tasks_root / "first.json").write_text(
        json.dumps(
            {
                "task_id": "task-duplicate",
                "title": "First definition",
                "summary": "Placeholder summary for duplicate detection.",
            }
        ),
        encoding="utf-8",
    )
    (tasks_root / "second.json").write_text(
        json.dumps(
            [
                {
                    "task_id": "task-duplicate",
                    "title": "Second definition",
                    "summary": "This should conflict with the first definition.",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(TaskSpecLoadingError) as excinfo:
        load_task_specs(tasks_root)

    assert "Duplicate task_id" in str(excinfo.value)
