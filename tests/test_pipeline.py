from __future__ import annotations

import os
import unittest
from unittest import mock

from agent.core import pipeline
from agent.core.llm_client import LLMClient


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
            with self.assertRaises(pipeline.LLMCallError):
                pipeline._call_model_json(  # type: ignore[protected-access]
                    LLMClient(provider="test", client=DummyClient(), supports_quota=False),
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
                with self.assertRaises(pipeline.LLMCallError):
                    pipeline._call_model_json(  # type: ignore[protected-access]
                        LLMClient(provider="test", client=DummyClient(), supports_quota=False),
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

    def test_call_model_json_warns_and_recovers_from_json_parse_failure(self) -> None:
        class SuccessfulResponses:
            def create(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                class Response:
                    id = "resp_1"
                    status = "completed"
                    output_text = "{\"invalid\": true"
                    usage = {
                        "input_tokens": 5,
                        "output_tokens": 7,
                        "total_tokens": 12,
                    }

                return Response()

        class DummyClient:
            responses = SuccessfulResponses()

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

        with mock.patch.object(pipeline, "append_event", side_effect=fake_append_event):
            payload, usage = pipeline._call_model_json(  # type: ignore[protected-access]
                LLMClient(provider="test", client=DummyClient(), supports_quota=False),
                system_prompt="sys",
                user_prompt="user",
                stage="retrieval_brief",
            )

        self.assertEqual(payload, {})
        self.assertIsInstance(usage, pipeline.StageUsage)
        self.assertEqual(usage.input_tokens, 5)
        self.assertEqual(usage.output_tokens, 7)
        self.assertEqual(usage.total_tokens, 12)

        warning_events = [event for event in captured if event["message"] == "model_json_parse_failed"]
        self.assertEqual(len(warning_events), 1)
        warning_details = warning_events[0]["details"]
        self.assertEqual(warning_details["stage"], "retrieval_brief")
        self.assertEqual(warning_details["attempt"], 1)
        self.assertEqual(warning_details["excerpt"], "{\"invalid\": true")
        self.assertEqual(warning_details["error_type"], "JSONDecodeError")

        completion_events = [event for event in captured if event["message"] == "model_call_completed"]
        self.assertEqual(len(completion_events), 1)


if __name__ == "__main__":
    unittest.main()
