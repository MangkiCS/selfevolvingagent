from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.task_context import TaskContextError, build_task_prompt, load_task_batch


class TaskContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tasks_dir = Path(__file__).resolve().parents[1] / 'tasks'

    def test_load_task_batch_partitions_ready_and_blocked(self) -> None:
        batch = load_task_batch(self.tasks_dir)

        self.assertEqual(
            [spec.task_id for spec in batch.ready],
            ['orchestrator/load-task-specs'],
        )
        self.assertEqual(
            [spec.task_id for spec in batch.blocked],
            ['orchestrator/replace-example-fallback'],
        )

        blocked_spec = batch.blocked[0]
        self.assertEqual(
            batch.missing_dependencies(blocked_spec),
            ('orchestrator/load-task-specs',),
        )

    def test_load_task_batch_marks_dependencies_satisfied(self) -> None:
        batch = load_task_batch(
            self.tasks_dir,
            completed={'orchestrator/load-task-specs'},
        )

        self.assertEqual(
            [spec.task_id for spec in batch.ready],
            ['orchestrator/load-task-specs', 'orchestrator/replace-example-fallback'],
        )
        self.assertEqual(batch.blocked, ())
        self.assertEqual(batch.completed, ('orchestrator/load-task-specs',))

    def test_build_task_prompt_formats_sections(self) -> None:
        batch = load_task_batch(self.tasks_dir)
        prompt = build_task_prompt(batch, ready_limit=3, blocked_limit=3)

        self.assertIn('## Ready Tasks', prompt)
        self.assertIn('orchestrator/load-task-specs', prompt)
        self.assertIn('## Blocked Tasks', prompt)
        self.assertIn('Blocked by: orchestrator/load-task-specs', prompt)

    def test_build_task_prompt_validates_limits(self) -> None:
        batch = load_task_batch(self.tasks_dir)
        with self.assertRaises(ValueError):
            build_task_prompt(batch, ready_limit=0)
        with self.assertRaises(ValueError):
            build_task_prompt(batch, blocked_limit=0)

    def test_load_task_batch_missing_directory_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / 'missing-tasks'
            with self.assertRaises(TaskContextError):
                load_task_batch(missing)


if __name__ == '__main__':
    unittest.main()
