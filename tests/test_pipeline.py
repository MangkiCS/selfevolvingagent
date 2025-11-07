from __future__ import annotations

import os
import unittest
from unittest import mock

from agent.core import pipeline


class PipelineModelCallTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict(
            os.environ,
            {
                "AGENT_EVENT_LOG_PATH": os.devnull,
                "OPENAI_API_MAX_RETRIES": "1",
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_call_model_json_logs_stage_and_error_type_on_failure(self) -> None:
        class FailingResponses:
            def create(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("x" * (pipeline.ERROR_MESSAGE_MAX_LENGTH + 20))

        class DummyClient:
            responses = FailingResponses()

        captured = []

        def fake_append_event(*, level, source, message, details=None):  # type: ignore[no-untyped-def]
            captured.append({
                "level": level,
                "source": source,
                "message": message,
                "details": details or {},
            })
            return captured[-1]

        with mock.patch.object(pipeline, "append_event", side_effect=fake_append_event):
            with self.assertRaises(RuntimeError):
                pipeline._call_model_json(  # type: ignore[protected-access]
                    DummyClient(),
                    system_prompt="sys",
                    user_prompt="user",
                    stage="execution_plan",
                )

        self.assertEqual(len(captured), 1)
        event = captured[0]
        self.assertEqual(event["message"], "LLM call attempt failed")
        details = event["details"]
        self.assertEqual(details["stage"], "execution_plan")
        self.assertEqual(details["error_type"], "RuntimeError")
        self.assertLessEqual(len(details["error"]), pipeline.ERROR_MESSAGE_MAX_LENGTH)
        self.assertTrue(details["error"].endswith("…"))


if __name__ == "__main__":
    unittest.main()
