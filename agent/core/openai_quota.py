"""Helpers for retrieving OpenAI account usage and rate-limit information."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from openai import OpenAI

from .event_log import append_event


@dataclass
class QuotaSnapshot:
    """Lightweight container for usage and limit metadata."""

    usage: Optional[Dict[str, Any]] = None
    limits: Optional[Dict[str, Any]] = None

    def is_empty(self) -> bool:
        return not (self.usage or self.limits)


def capture_quota_snapshot(
    client: OpenAI,
    *,
    request_timeout: float,
    include_usage: bool = True,
    include_limits: bool = True,
) -> QuotaSnapshot:
    """Fetch usage and rate-limit data before firing an expensive request.

    The OpenAI REST API exposes lightweight read-only endpoints that expose
    per-project usage totals (``GET /v1/usage``) and rate-limit metadata
    (``GET /v1/limits``).  Polling these endpoints before kicking off an LLM
    call lets us surface quota/limit information alongside the usual token
    accounting, which helps operators diagnose throttling or budgeting
    problems before a stage runs.
    """

    usage: Optional[Dict[str, Any]] = None
    limits: Optional[Dict[str, Any]] = None

    if include_usage:
        today = _dt.date.today().isoformat()
        usage = _safe_get_json(
            client,
            path="/usage",
            options={"timeout": request_timeout, "params": {"date": today}},
        )
        usage = _summarise_usage_payload(usage)

    if include_limits:
        limits = _safe_get_json(
            client,
            path="/limits",
            options={"timeout": request_timeout},
        )
        limits = _summarise_limits_payload(limits)

    return QuotaSnapshot(usage=usage, limits=limits)


def _safe_get_json(
    client: OpenAI,
    *,
    path: str,
    options: Mapping[str, Any],
) -> Optional[Mapping[str, Any]]:
    try:
        response = client.get(path, cast_to=dict, options=dict(options))
    except Exception as exc:  # pragma: no cover - defensive logging only
        append_event(
            level="warning",
            source="openai_quota",
            message="request_failed",
            details={"path": path, "error": str(exc)},
        )
        return None

    if isinstance(response, Mapping):
        return response
    return None


def _summarise_usage_payload(payload: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return None

    summary: Dict[str, Any] = {}

    totals = payload.get("aggregated_usage") or payload.get("total_usage")
    if isinstance(totals, Mapping):
        summary["totals"] = _extract_numeric_blocks(totals)

    credits = payload.get("credits") or payload.get("credit_summary")
    if isinstance(credits, Mapping):
        summary["credits"] = _extract_numeric_blocks(credits)

    operations = []
    for entry in payload.get("data", []):
        if not isinstance(entry, Mapping):
            continue
        item: Dict[str, Any] = {}
        for key in ("operation", "model", "aggregation_timestamp"):
            value = entry.get(key)
            if value is not None:
                item[key] = value
        metrics = _extract_numeric_blocks(entry)
        if metrics:
            item["metrics"] = metrics
        if item:
            operations.append(item)
        if len(operations) >= 5:
            break
    if operations:
        summary["operations"] = operations

    return summary or None


def _summarise_limits_payload(payload: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return None

    summary: Dict[str, Any] = {}

    if isinstance(payload.get("object"), str):
        summary["object"] = payload["object"]

    entries = []
    for entry in payload.get("data", []):
        if not isinstance(entry, Mapping):
            continue
        item: Dict[str, Any] = {}
        for key in ("name", "scope", "model", "type", "reset_seconds"):
            value = entry.get(key)
            if value is not None:
                item[key] = value
        metrics = _extract_numeric_blocks(entry)
        if metrics:
            item["metrics"] = metrics
        if item:
            entries.append(item)
        if len(entries) >= 5:
            break

    if entries:
        summary["limits"] = entries

    return summary or None


def _extract_numeric_blocks(block: Mapping[str, Any]) -> Dict[str, Any]:
    numeric: Dict[str, Any] = {}
    for key, value in block.items():
        if isinstance(value, (int, float)):
            numeric[key] = value
        elif isinstance(value, Mapping):
            nested = {k: v for k, v in value.items() if isinstance(v, (int, float))}
            if nested:
                numeric[key] = nested
    return numeric
