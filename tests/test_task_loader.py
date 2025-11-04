from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.core.task_loader import TaskSpecLoadingError, load_task_specs


class LoadTaskSpecsTests(unittest.TestCase):
    def test_load_task_specs_from_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_root = Path(tmpdir) / "tasks"
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

            self.assertEqual(
                [spec.task_id for spec in specs],
                ["task-alpha", "task-beta", "task-gamma"],
            )
            self.assertTrue(specs[0].has_acceptance_criteria())
            self.assertEqual(specs[-1].priority, "high")

    def test_load_task_specs_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_root = Path(tmpdir) / "tasks"
            tasks_root.mkdir()
            (tasks_root / "broken.json").write_text("{ invalid json }", encoding="utf-8")

            with self.assertRaises(TaskSpecLoadingError) as ctx:
                load_task_specs(tasks_root)

            self.assertIn("Invalid JSON payload", str(ctx.exception))

    def test_load_task_specs_duplicate_task_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_root = Path(tmpdir) / "tasks"
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

            with self.assertRaises(TaskSpecLoadingError) as ctx:
                load_task_specs(tasks_root)

            self.assertIn("Duplicate task_id", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
