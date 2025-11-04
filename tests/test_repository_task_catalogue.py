from __future__ import annotations

import unittest
from pathlib import Path

from agent.core.task_loader import load_task_specs


class RepositoryTaskCatalogueTests(unittest.TestCase):
    def test_repository_task_catalogue_loads(self) -> None:
        tasks_dir = Path(__file__).resolve().parents[1] / "tasks"
        specs = load_task_specs(tasks_dir)

        task_ids = [spec.task_id for spec in specs]
        self.assertEqual(
            task_ids,
            ["orchestrator/load-task-specs", "orchestrator/replace-example-fallback"],
        )

        integrate_spec = specs[0]
        self.assertEqual(integrate_spec.priority, "high")
        self.assertTrue(integrate_spec.acceptance_criteria)
        self.assertIn("TaskSpec", integrate_spec.summary)

        replace_spec = specs[1]
        self.assertEqual(
            replace_spec.dependencies, ("orchestrator/load-task-specs",)
        )


if __name__ == "__main__":
    unittest.main()
