from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent.core import event_log


class EventLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.log_path = Path(self._tmpdir.name) / "log.json"
        patcher = mock.patch.dict(os.environ, {"AGENT_EVENT_LOG_PATH": str(self.log_path)})
        patcher.start()
        self.addCleanup(patcher.stop)
        event_log.clear_events(self.log_path)

    def test_append_and_load_events(self) -> None:
        stored = event_log.append_event(
            level="error",
            source="unit_test",
            message="Something failed",
            details={"code": 123},
        )
        self.assertEqual(stored["level"], "error")
        self.assertEqual(stored["message"], "Something failed")

        events = event_log.load_events(self.log_path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source"], "unit_test")
        self.assertEqual(events[0]["details"], {"code": 123})

        raw = self.log_path.read_text(encoding="utf-8")
        loaded = json.loads(raw)
        self.assertIsInstance(loaded, list)

    def test_event_log_truncates_to_max(self) -> None:
        for idx in range(event_log.MAX_EVENTS + 5):
            event_log.append_event(level="error", source="s", message=f"m{idx}")

        events = event_log.load_events(self.log_path)
        self.assertEqual(len(events), event_log.MAX_EVENTS)
        self.assertEqual(events[0]["message"], "m5")
        self.assertEqual(events[-1]["message"], f"m{event_log.MAX_EVENTS + 4}")


if __name__ == "__main__":
    unittest.main()
