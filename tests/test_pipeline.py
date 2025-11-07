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

        self.assertEqual(len(captured), 2)
        failure_event = captured[0]
        self.assertEqual(failure_event["message"], "LLM call attempt failed")
        details = failure_event["details"]
        self.assertEqual(details["stage"], "execution_plan")
        self.assertEqual(details["error_type"], "RuntimeError")
        self.assertLessEqual(len(details["error"]), pipeline.ERROR_MESSAGE_MAX_LENGTH)
        self.assertTrue(details["error"].endswith("…"))

        exhaustion_event = captured[1]
        self.assertEqual(exhaustion_event["message"], "llm_call_exhausted")
        exhaustion_details = exhaustion_event["details"]
        self.assertEqual(exhaustion_details["stage"], "execution_plan")
        self.assertEqual(exhaustion_details["attempts"], 1)
        self.assertEqual(exhaustion_details["model"], pipeline.DEFAULT_MODEL)
        self.assertEqual(exhaustion_details["error_type"], "RuntimeError")
        self.assertLessEqual(
            len(exhaustion_details["error"]), pipeline.ERROR_MESSAGE_MAX_LENGTH
        )
        self.assertTrue(exhaustion_details["error"].endswith("…"))

    def test_call_model_json_records_exhaustion_after_retries(self) -> None:
        class FailingResponses:
            def create(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                raise TimeoutError("retriable failure")

        class DummyClient:
            responses = FailingResponses()

        captured = []

        def fake_append_event(*, level, source, message, details=None):  # type: ignore[no-untyped-def]
            captured.append(
                {
                    "level": level,
                    "source": source,
                    "message": message,
                    "details": details or {},
                }
            )
            return captured[-1]

        with mock.patch.dict(os.environ, {"OPENAI_API_MAX_RETRIES": "2"}):
            with mock.patch.object(pipeline, "append_event", side_effect=fake_append_event):
                with self.assertRaises(TimeoutError):
                    pipeline._call_model_json(  # type: ignore[protected-access]
                        DummyClient(),
                        system_prompt="sys",
                        user_prompt="user",
                        stage="context_summary",
                    )

        exhaustion_events = [e for e in captured if e["message"] == "llm_call_exhausted"]
        self.assertEqual(len(exhaustion_events), 1)
        details = exhaustion_events[0]["details"]
        self.assertEqual(details["stage"], "context_summary")
        self.assertEqual(details["attempts"], 2)
        self.assertEqual(details["model"], pipeline.DEFAULT_MODEL)
        self.assertEqual(details["error_type"], "TimeoutError")


if __name__ == "__main__":
    unittest.main()
