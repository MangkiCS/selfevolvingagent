"""LLM execution pipeline for multi-stage orchestration."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from openai import OpenAI

from agent.core.event_log import (
    append_event,
    log_stage_transition,
    log_token_usage,
)
from agent.core.vector_store import QueryResult, VectorStore


DEFAULT_MODEL = "gpt-5-codex"
DEFAULT_API_TIMEOUT = 1800.0
DEFAULT_API_MAX_RETRIES = 2
DEFAULT_API_POLL_INTERVAL = 1.5
DEFAULT_API_REQUEST_TIMEOUT = 30.0


@dataclass
class StageUsage:
    """Normalised token accounting for an LLM stage."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def is_empty(self) -> bool:
        return not any((self.input_tokens, self.output_tokens, self.total_tokens))

    def as_dict(self) -> Dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class ContextClue:
    """Context snippet derived during the summarisation stage."""

    identifier: str
    path: Optional[str]
    rationale: str
    content: str


@dataclass
class ContextSummary:
    """Structured result for the context-summarisation stage."""

    summary: str
    context_clues: List[ContextClue] = field(default_factory=list)
    usage: Optional[StageUsage] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass
class RetrievalBrief:
    """Structured retrieval hand-off for the execution stage."""

    brief: str
    selected_context_ids: List[str] = field(default_factory=list)
    focus_paths: List[str] = field(default_factory=list)
    handoff_notes: str = ""
    open_questions: List[str] = field(default_factory=list)
    retrieved_snippets: List[QueryResult] = field(default_factory=list)
    usage: Optional[StageUsage] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass
class ExecutionPlan:
    """Final plan returned by the code-generation stage."""

    rationale: str = ""
    plan: List[str] = field(default_factory=list)
    code_patches: List[Dict[str, Any]] = field(default_factory=list)
    new_tests: List[Dict[str, Any]] = field(default_factory=list)
    admin_requests: List[Dict[str, Any]] = field(default_factory=list)
    notes: str = ""
    usage: Optional[StageUsage] = None
    raw: Optional[Dict[str, Any]] = None

    def has_changes(self) -> bool:
        return bool(self.code_patches or self.new_tests)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rationale": self.rationale,
            "plan": self.plan,
            "code_patches": self.code_patches,
            "new_tests": self.new_tests,
            "admin_requests": self.admin_requests,
            "notes": self.notes,
        }


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _extract_response_text(parts: Optional[Iterable[object]]) -> str:
    if not parts:
        return ""
    chunks: List[str] = []
    for item in parts:
        if isinstance(item, dict):
            item_type = item.get("type")
            content = item.get("content")
        else:
            item_type = getattr(item, "type", None)
            content = getattr(item, "content", None)
        if item_type == "message":
            if not content:
                continue
            for segment in content:
                if isinstance(segment, dict):
                    segment_type = segment.get("type")
                    text = segment.get("text", "")
                else:
                    segment_type = getattr(segment, "type", None)
                    text = getattr(segment, "text", "")
                if segment_type == "output_text" and text:
                    chunks.append(text)
        elif item_type == "output_text":
            text = item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
            if text:
                chunks.append(text)
    return "".join(chunks)


def _normalise_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _ensure_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, Sequence):
        items: List[str] = []
        for entry in value:
            text = _normalise_text(entry)
            if text:
                items.append(text)
        return items
    return []


def _normalise_context_clues(raw: Any) -> List[ContextClue]:
    if not raw:
        return []
    clues: List[ContextClue] = []
    if not isinstance(raw, Sequence):
        raw = [raw]
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            identifier = _normalise_text(item.get("id")) or f"clue-{index}"
            path = _normalise_text(item.get("path")) or None
            rationale = _normalise_text(item.get("rationale")) or _normalise_text(
                item.get("reason")
            )
            content = _normalise_text(item.get("content"))
        else:
            identifier = f"clue-{index}"
            path = None
            rationale = ""
            content = _normalise_text(item)
        clues.append(
            ContextClue(
                identifier=identifier,
                path=path,
                rationale=rationale,
                content=content,
            )
        )
    return clues


def _extract_usage(response: Any) -> StageUsage:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return StageUsage()

    def _get(attr: str) -> int:
        if isinstance(usage, dict):
            value = usage.get(attr)
        else:
            value = getattr(usage, attr, None)
        if value is None and attr == "input_tokens":
            if isinstance(usage, dict):
                value = usage.get("prompt_tokens")
            else:
                value = getattr(usage, "prompt_tokens", None)
        if value is None and attr == "output_tokens":
            if isinstance(usage, dict):
                value = usage.get("completion_tokens")
            else:
                value = getattr(usage, "completion_tokens", None)
        if isinstance(value, (int, float)):
            return int(value)
        try:
            return int(value)  # type: ignore[arg-type]
        except Exception:
            return 0

    return StageUsage(
        input_tokens=_get("input_tokens"),
        output_tokens=_get("output_tokens"),
        total_tokens=_get("total_tokens"),
    )


def _call_model_json(
    client: OpenAI,
    *,
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
) -> Tuple[Dict[str, Any], StageUsage]:
    timeout = _env_float("OPENAI_API_TIMEOUT", DEFAULT_API_TIMEOUT)
    max_retries = max(1, _env_int("OPENAI_API_MAX_RETRIES", DEFAULT_API_MAX_RETRIES))
    poll_interval = max(0.2, _env_float("OPENAI_API_POLL_INTERVAL", DEFAULT_API_POLL_INTERVAL))
    request_timeout = max(1.0, _env_float("OPENAI_API_REQUEST_TIMEOUT", DEFAULT_API_REQUEST_TIMEOUT))

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            deadline = time.monotonic() + timeout
            response = client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                background=True,
                timeout=min(request_timeout, timeout),
            )

            response_id = getattr(response, "id", None)
            status = getattr(response, "status", None)
            while status in (None, "queued", "in_progress"):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("LLM call exceeded configured timeout")
                time.sleep(min(poll_interval, remaining))
                if not response_id:
                    break
                response = client.responses.retrieve(
                    response_id,
                    timeout=min(request_timeout, max(remaining, 0.1)),
                )
                status = getattr(response, "status", None)

            if status == "completed":
                text = getattr(response, "output_text", None)
                if not text:
                    text = _extract_response_text(getattr(response, "output", None))
                payload: Dict[str, Any]
                if text:
                    try:
                        payload = json.loads(text)
                    except Exception:
                        payload = {}
                else:
                    payload = {}
                return payload, _extract_usage(response)

            if status == "failed" and getattr(response, "error", None):
                err = getattr(response, "error")
                message = getattr(err, "message", repr(err))
                raise RuntimeError(f"Model response failed: {message}")

            raise RuntimeError(f"Model response did not complete (status={status})")
        except Exception as exc:  # pragma: no cover - defensive logging
            last_error = exc
            append_event(
                level="warning",
                source="pipeline",
                message="LLM call attempt failed",
                details={"attempt": attempt, "error": str(exc)},
            )
            if attempt < max_retries:
                sleep_seconds = min(2 ** (attempt - 1), 5)
                time.sleep(sleep_seconds)

    if last_error:
        raise last_error
    return {}, StageUsage()


def run_context_summary(
    client: OpenAI,
    *,
    system_prompt: str,
    user_prompt: str,
) -> ContextSummary:
    stage_name = "context_summary"
    log_stage_transition(stage_name, "start")
    payload, usage = _call_model_json(client, system_prompt=system_prompt, user_prompt=user_prompt)
    summary = _normalise_text(payload.get("summary") or payload.get("context_summary"))
    clues = _normalise_context_clues(payload.get("context_clues"))
    result = ContextSummary(summary=summary, context_clues=clues, usage=usage, raw=payload)
    log_stage_transition(stage_name, "complete", metadata={"context_clues": len(clues)})
    if usage and not usage.is_empty():
        log_token_usage(stage_name, usage=usage.as_dict())
    return result


def run_retrieval_brief(
    client: OpenAI,
    *,
    system_prompt: str,
    user_prompt: str,
    vector_store: Optional[VectorStore] = None,
    query_text: Optional[str] = None,
    max_snippets: int = 3,
) -> RetrievalBrief:
    stage_name = "retrieval_brief"
    log_stage_transition(stage_name, "start")
    payload, usage = _call_model_json(client, system_prompt=system_prompt, user_prompt=user_prompt)
    brief = _normalise_text(payload.get("brief") or payload.get("retrieval_brief"))
    selected_ids = _ensure_str_list(
        payload.get("selected_context_ids") or payload.get("context_ids")
    )
    focus_paths = _ensure_str_list(payload.get("focus_paths") or payload.get("target_files"))
    handoff_notes = _normalise_text(payload.get("handoff_notes"))
    open_questions = _ensure_str_list(payload.get("open_questions"))
    snippets: List[QueryResult] = []
    search_basis = query_text or brief
    if vector_store and search_basis:
        try:
            snippets = vector_store.query_text(search_basis, top_k=max_snippets)
        except Exception as exc:  # pragma: no cover - defensive path
            append_event(
                level="warning",
                source="pipeline",
                message="Vector store query failed",
                details={"error": str(exc)},
            )
            snippets = []

    result = RetrievalBrief(
        brief=brief,
        selected_context_ids=selected_ids,
        focus_paths=focus_paths,
        handoff_notes=handoff_notes,
        open_questions=open_questions,
        retrieved_snippets=snippets,
        usage=usage,
        raw=payload,
    )
    log_stage_transition(stage_name, "complete", metadata={"focus_paths": len(focus_paths)})
    if usage and not usage.is_empty():
        log_token_usage(stage_name, usage=usage.as_dict())
    return result


def _normalise_plan_steps(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, Sequence):
        steps: List[str] = []
        for entry in value:
            text = _normalise_text(entry)
            if text:
                steps.append(text)
        return steps
    return []


def _normalise_patch_list(value: Any) -> List[Dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, list):
        patches: List[Dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict) and item.get("path") and item.get("content") is not None:
                patches.append({"path": item["path"], "content": item["content"]})
        return patches
    return []


def _normalise_admin_requests(value: Any) -> List[Dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, list):
        requests: List[Dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                requests.append(item)
        return requests
    return []


def run_execution_plan(
    client: OpenAI,
    *,
    system_prompt: str,
    user_prompt: str,
) -> ExecutionPlan:
    stage_name = "execution_plan"
    log_stage_transition(stage_name, "start")
    payload, usage = _call_model_json(client, system_prompt=system_prompt, user_prompt=user_prompt)
    plan = ExecutionPlan(
        rationale=_normalise_text(payload.get("rationale")),
        plan=_normalise_plan_steps(payload.get("plan")),
        code_patches=_normalise_patch_list(payload.get("code_patches")),
        new_tests=_normalise_patch_list(payload.get("new_tests")),
        admin_requests=_normalise_admin_requests(payload.get("admin_requests")),
        notes=_normalise_text(payload.get("notes")),
        usage=usage,
        raw=payload,
    )
    log_stage_transition(
        stage_name,
        "complete",
        metadata={"patches": len(plan.code_patches), "tests": len(plan.new_tests)},
    )
    if usage and not usage.is_empty():
        log_token_usage(stage_name, usage=usage.as_dict())
    return plan

