from __future__ import annotations

import unittest

from agent.core.taskspec import TaskSpec


class TaskSpecTests(unittest.TestCase):
    def test_taskspec_from_dict_roundtrip(self) -> None:
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

        self.assertEqual(spec.task_id, "task-001")
        self.assertEqual(spec.priority, "high")
        self.assertEqual(
            spec.details,
            "Provide disk-backed loading for automated planning.",
        )
        self.assertTrue(spec.has_acceptance_criteria())

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
        self.assertEqual(spec.to_dict(), expected)

    def test_taskspec_requires_identifier(self) -> None:
        with self.assertRaises(ValueError):
            TaskSpec.from_dict(
                {"task_id": "   ", "title": "Write plan", "summary": "Ensure run plan is recorded."}
            )

    def test_taskspec_rejects_unknown_priority(self) -> None:
        with self.assertRaises(ValueError):
            TaskSpec.from_dict(
                {
                    "task_id": "task-003",
                    "title": "Investigate priority handling",
                    "summary": "Ensure invalid priorities fail fast.",
                    "priority": "urgent",
                }
            )

    def test_taskspec_normalises_sequences_on_init(self) -> None:
        spec = TaskSpec(
            task_id="task-004",
            title="Document spec",
            summary="Produce authoring guidelines for TaskSpec.",
            acceptance_criteria=(" Document fields ",),
            tags="documentation",
        )

        self.assertEqual(spec.acceptance_criteria, ("Document fields",))
        self.assertEqual(spec.tags, ("documentation",))
        self.assertTrue(spec.has_acceptance_criteria())
        self.assertFalse(spec.dependencies)
        self.assertFalse(spec.context)


if __name__ == "__main__":
    unittest.main()
