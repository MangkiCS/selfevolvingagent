from __future__ import annotations

import pytest

from agent.core.taskspec import TaskSpec


def test_taskspec_from_dict_roundtrip() -> None:
    payload = {
        "task_id": "task-001",
        "title": "Implement backlog loader",
        "summary": "Convert persisted task definitions into TaskSpec instances.",
        "details": "  Provide disk-backed loading for automated planning. ",
        "context": [
            "docs/backlog.md",
            "docs/task_spec.md",
        ],
        "acceptance_criteria": [
            "Loader yields TaskSpec objects for each enabled task definition.",
            "Gracefully handles missing or malformed task files.",
        ],
        "priority": "High",
        "tags": ["planning", "infrastructure"],
        "dependencies": [],
    }

    spec = TaskSpec.from_dict(payload)

    assert spec.task_id == "task-001"
    assert spec.priority == "high"
    assert spec.details == "Provide disk-backed loading for automated planning."
    assert spec.has_acceptance_criteria()

    expected = {
        "task_id": "task-001",
        "title": "Implement backlog loader",
        "summary": "Convert persisted task definitions into TaskSpec instances.",
        "details": "Provide disk-backed loading for automated planning.",
        "context": ["docs/backlog.md", "docs/task_spec.md"],
        "acceptance_criteria": [
            "Loader yields TaskSpec objects for each enabled task definition.",
            "Gracefully handles missing or malformed task files.",
        ],
        "priority": "high",
        "tags": ["planning", "infrastructure"],
        "dependencies": [],
    }
    assert spec.to_dict() == expected


def test_taskspec_requires_identifier() -> None:
    with pytest.raises(ValueError):
        TaskSpec.from_dict(
            {"task_id": "   ", "title": "Write plan", "summary": "Ensure run plan is recorded."}
        )


def test_taskspec_rejects_unknown_priority() -> None:
    with pytest.raises(ValueError):
        TaskSpec.from_dict(
            {
                "task_id": "task-003",
                "title": "Investigate priority handling",
                "summary": "Ensure invalid priorities fail fast.",
                "priority": "urgent",
            }
        )


def test_taskspec_normalises_sequences_on_init() -> None:
    spec = TaskSpec(
        task_id="task-004",
        title="Document spec",
        summary="Produce authoring guidelines for TaskSpec.",
        acceptance_criteria=(" Document fields ",),
        tags="documentation",
    )

    assert spec.acceptance_criteria == ("Document fields",)
    assert spec.tags == ("documentation",)
    assert spec.has_acceptance_criteria()
    assert not spec.dependencies
    assert not spec.context
