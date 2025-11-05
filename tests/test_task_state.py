from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.core.task_state import CompletedTaskStore, TaskStateError, load_completed_tasks


class CompletedTaskStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.state_path = Path(self._tmpdir.name) / 'task_state.json'

    def test_missing_file_loads_empty_state(self) -> None:
        store = CompletedTaskStore(path=self.state_path)
        self.assertEqual(store.completed, ())
        self.assertFalse(self.state_path.exists())
        self.assertFalse(store.is_completed('orchestrator/replace-example-fallback'))

    def test_mark_completed_persists_and_reloads(self) -> None:
        store = CompletedTaskStore(path=self.state_path)
        store.mark_completed('planning/task-loader')
        store.mark_completed('planning/task-loader')  # idempotent
        store.mark_completed('orchestrator/replace-example-fallback')

        self.assertTrue(self.state_path.exists())
        reloaded = CompletedTaskStore(path=self.state_path)
        self.assertEqual(
            set(reloaded.completed),
            {'planning/task-loader', 'orchestrator/replace-example-fallback'},
        )
        self.assertTrue(reloaded.is_completed('planning/task-loader'))

    def test_normalises_and_validates_task_identifiers(self) -> None:
        store = CompletedTaskStore(path=self.state_path)
        store.mark_completed('  planning/normalise  ')

        self.assertTrue(store.is_completed('planning/normalise'))
        reloaded = CompletedTaskStore(path=self.state_path)
        self.assertEqual(reloaded.completed, ('planning/normalise',))

        with self.assertRaises(ValueError):
            store.mark_completed('   ')

    def test_mark_incomplete_and_clear(self) -> None:
        store = CompletedTaskStore(path=self.state_path)
        store.mark_completed('task/a')
        store.mark_completed('task/b')

        store.mark_incomplete('task/a')
        self.assertFalse(store.is_completed('task/a'))

        reloaded = CompletedTaskStore(path=self.state_path)
        self.assertEqual(reloaded.completed, ('task/b',))

        store.clear()
        self.assertEqual(store.completed, ())
        raw = json.loads(self.state_path.read_text(encoding='utf-8'))
        self.assertEqual(raw['completed'], [])

    def test_invalid_json_raises_task_state_error(self) -> None:
        self.state_path.write_text('{ invalid json }', encoding='utf-8')
        with self.assertRaises(TaskStateError):
            CompletedTaskStore(path=self.state_path)

    def test_invalid_structure_raises_task_state_error(self) -> None:
        self.state_path.write_text(json.dumps({'completed': 'oops'}), encoding='utf-8')
        with self.assertRaises(TaskStateError):
            load_completed_tasks(self.state_path)

    def test_load_completed_tasks_function(self) -> None:
        store = CompletedTaskStore(path=self.state_path)
        store.mark_completed('task/alpha')
        store.mark_completed('task/beta')

        loaded = load_completed_tasks(self.state_path)
        self.assertEqual(loaded, ('task/alpha', 'task/beta'))


if __name__ == '__main__':
    unittest.main()
