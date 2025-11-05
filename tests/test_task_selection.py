from __future__ import annotations

import unittest

from agent.core.task_selection import (
    order_by_priority,
    select_next_task,
    summarise_tasks_for_prompt,
)
from agent.core.taskspec import TaskSpec


class TaskSelectionTests(unittest.TestCase):
    def test_order_by_priority_preserves_relative_order(self) -> None:
        specs = [
            TaskSpec(task_id="low-1", title="Low 1", summary="Low priority work", priority="low"),
            TaskSpec(task_id="critical-1", title="Critical 1", summary="Critical priority work", priority="critical"),
            TaskSpec(task_id="medium-1", title="Medium 1", summary="Medium priority work", priority="medium"),
            TaskSpec(task_id="high-1", title="High 1", summary="High priority work", priority="high"),
            TaskSpec(task_id="low-2", title="Low 2", summary="Another low priority", priority="low"),
        ]

        ordered = order_by_priority(specs)

        self.assertEqual(
            [spec.task_id for spec in ordered],
            ["critical-1", "high-1", "medium-1", "low-1", "low-2"],
        )

    def test_select_next_task_respects_dependencies(self) -> None:
        specs = [
            TaskSpec(
                task_id="foundation",
                title="Foundation work",
                summary="Provide groundwork",
                priority="high",
            ),
            TaskSpec(
                task_id="dependent",
                title="Dependent work",
                summary="Requires foundation",
                priority="critical",
                dependencies=("foundation",),
            ),
        ]

        first = select_next_task(specs, completed=set())
        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(first.task_id, "foundation")

        second = select_next_task(specs, completed={"foundation"})
        self.assertIsNotNone(second)
        assert second is not None
        self.assertEqual(second.task_id, "dependent")

    def test_select_next_task_returns_none_when_blocked(self) -> None:
        specs = [
            TaskSpec(
                task_id="blocked",
                title="Blocked work",
                summary="Depends on something missing",
                priority="high",
                dependencies=("unknown",),
            )
        ]

        next_task = select_next_task(specs, completed={"other"})
        self.assertIsNone(next_task)

    def test_summarise_tasks_for_prompt_formats_entries(self) -> None:
        specs = [
            TaskSpec(
                task_id="task-a",
                title="Task A",
                summary="Implement ability A",
                priority="high",
                acceptance_criteria=("Criterion A1", "Criterion A2"),
            ),
            TaskSpec(
                task_id="task-b",
                title="Task B",
                summary="Implement ability B",
                priority="medium",
                dependencies=("task-a",),
            ),
        ]

        summary = summarise_tasks_for_prompt(specs, limit=2)

        self.assertIn("- [high] task-a: Implement ability A", summary)
        self.assertIn("  * Criterion A1", summary)
        self.assertIn("  * Criterion A2", summary)
        self.assertIn("- [medium] task-b: Implement ability B", summary)
        self.assertIn("  * No acceptance criteria recorded.", summary)
        self.assertIn("  * Dependencies: task-a", summary)

    def test_summarise_tasks_for_prompt_validates_limit(self) -> None:
        with self.assertRaises(ValueError):
            summarise_tasks_for_prompt([], limit=0)

    def test_summarise_tasks_for_prompt_handles_empty_input(self) -> None:
        summary = summarise_tasks_for_prompt([], limit=3)
        self.assertEqual(summary, "No pending tasks.")


if __name__ == "__main__":
    unittest.main()
