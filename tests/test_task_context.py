from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.core.task_context import (
    TaskContextError,
    TaskPrompt,
    build_task_prompt,
    load_task_batch,
    load_task_prompt,
)


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
        self.assertNotIn('## Completed Tasks', prompt)

    def test_build_task_prompt_validates_limits(self) -> None:
        batch = load_task_batch(self.tasks_dir)
        with self.assertRaises(ValueError):
            build_task_prompt(batch, ready_limit=0)
        with self.assertRaises(ValueError):
            build_task_prompt(batch, blocked_limit=0)

    def test_build_task_prompt_includes_completed_section(self) -> None:
        batch = load_task_batch(
            self.tasks_dir,
            completed={'orchestrator/load-task-specs'},
        )
        prompt = build_task_prompt(batch)

        self.assertIn('## Completed Tasks', prompt)
        self.assertIn('- orchestrator/load-task-specs', prompt)

    def test_load_task_prompt_returns_payload(self) -> None:
        payload = load_task_prompt(self.tasks_dir, ready_limit=1, blocked_limit=1)

        self.assertIsInstance(payload, TaskPrompt)
        self.assertTrue(payload.has_ready_tasks())
        self.assertEqual(
            [spec.task_id for spec in payload.ready],
            ['orchestrator/load-task-specs'],
        )
        self.assertEqual(
            [spec.task_id for spec in payload.blocked],
            ['orchestrator/replace-example-fallback'],
        )
        self.assertIn('## Ready Tasks', payload.prompt)
        self.assertIn('## Blocked Tasks', payload.prompt)

    def test_task_prompt_to_dict_contains_metadata(self) -> None:
        payload = load_task_prompt(self.tasks_dir)
        summary = payload.to_dict()

        self.assertEqual(
            summary['ready_task_ids'],
            ['orchestrator/load-task-specs'],
        )
        self.assertEqual(
            summary['blocked_task_ids'],
            ['orchestrator/replace-example-fallback'],
        )
        self.assertEqual(summary['completed_task_ids'], [])
        self.assertIn('## Ready Tasks', summary['prompt'])

    def test_load_task_prompt_respects_completed_ids(self) -> None:
        payload = load_task_prompt(
            self.tasks_dir,
            completed={'orchestrator/load-task-specs'},
        )

        self.assertEqual(
            [spec.task_id for spec in payload.ready],
            ['orchestrator/load-task-specs', 'orchestrator/replace-example-fallback'],
        )
        self.assertEqual(payload.blocked, ())
        self.assertEqual(payload.completed, ('orchestrator/load-task-specs',))

    def test_load_task_prompt_reads_completed_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / 'task_state.json'
            state_path.write_text(
                json.dumps({'completed': ['orchestrator/load-task-specs']}),
                encoding='utf-8',
            )

            payload = load_task_prompt(self.tasks_dir, state_path=state_path)

        self.assertEqual(payload.completed, ('orchestrator/load-task-specs',))
        self.assertEqual(
            [spec.task_id for spec in payload.ready],
            ['orchestrator/load-task-specs', 'orchestrator/replace-example-fallback'],
        )
        self.assertTrue(payload.has_ready_tasks())

    def test_load_task_prompt_raises_on_invalid_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / 'task_state.json'
            state_path.write_text('{ invalid json }', encoding='utf-8')

            with self.assertRaises(TaskContextError):
                load_task_prompt(self.tasks_dir, state_path=state_path)

    def test_load_task_prompt_raises_when_directory_missing(self) -> None:
        missing_dir = self.tasks_dir / 'missing'

        with self.assertRaises(TaskContextError):
            load_task_prompt(missing_dir)

    def test_load_task_prompt_raises_when_path_is_not_directory(self) -> None:
        task_file = self.tasks_dir / 'active.json'

        with self.assertRaises(TaskContextError):
            load_task_prompt(task_file)


if __name__ == '__main__':
    unittest.main()
