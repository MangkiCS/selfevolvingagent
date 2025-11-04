from __future__ import annotations

from pathlib import Path

from agent.core.task_loader import load_task_specs


def test_repository_task_catalogue_loads() -> None:
    tasks_dir = Path(__file__).resolve().parents[1] / "tasks"
    specs = load_task_specs(tasks_dir)

    task_ids = [spec.task_id for spec in specs]
    assert task_ids == [
        "orchestrator/load-task-specs",
        "orchestrator/replace-example-fallback",
    ]

    integrate_spec = specs[0]
    assert integrate_spec.priority == "high"
    assert integrate_spec.acceptance_criteria
    assert "TaskSpec" in integrate_spec.summary

    replace_spec = specs[1]
    assert replace_spec.dependencies == ("orchestrator/load-task-specs",)
