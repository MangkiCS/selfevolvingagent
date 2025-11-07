"""Persistent event log utilities for orchestrator runs."""
from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_LOG_PATH = ROOT / "docs" / "run_events.json"
MAX_EVENTS = 200


def _resolve_log_path(path: Optional[pathlib.Path] = None) -> pathlib.Path:
    """Return the path where events should be persisted."""
    if path is not None:
        return path
    override = os.environ.get("AGENT_EVENT_LOG_PATH")
    if override:
        return pathlib.Path(override)
    return DEFAULT_LOG_PATH


def load_events(path: Optional[pathlib.Path] = None) -> List[Dict[str, Any]]:
    """Load all stored events, returning an empty list on failure."""
    log_path = _resolve_log_path(path)
    if not log_path.exists():
        return []
    try:
        data = json.loads(log_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [event for event in data if isinstance(event, dict)]
    return []


def _truncate(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only the most recent MAX_EVENTS entries."""
    events_list = [event for event in events if isinstance(event, dict)]
    if len(events_list) <= MAX_EVENTS:
        return events_list
    return events_list[-MAX_EVENTS:]


def append_event(
    *,
    level: str,
    source: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    path: Optional[pathlib.Path] = None,
) -> Dict[str, Any]:
    """Append an event to the persistent log and return the stored entry."""
    log_path = _resolve_log_path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "source": source,
        "message": message,
    }
    if details:
        entry["details"] = details

    events = load_events(log_path)
    events.append(entry)
    events = _truncate(events)
    log_path.write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return entry


def log_admin_requests(
    requests: Sequence[Mapping[str, Any]] | Sequence[Any],
    *,
    path: Optional[pathlib.Path] = None,
) -> Optional[Dict[str, Any]]:
    """Persist admin assistance requests to the event log.

    The model may emit arbitrary objects inside ``admin_requests``.  We only
    record well-formed mapping entries to avoid polluting the log with
    unexpected scalars while still surfacing the relevant metadata.
    """

    if not requests:
        return None

    normalised: List[Dict[str, Any]] = []
    for item in requests:
        if isinstance(item, Mapping):
            normalised.append(dict(item))

    if not normalised:
        return None

    details: Dict[str, Any] = {"count": len(normalised), "requests": normalised}
    return append_event(
        level="warning",
        source="admin_channel",
        message="admin_requests",
        details=details,
        path=path,
    )


def clear_events(path: Optional[pathlib.Path] = None) -> None:
    """Remove all stored events."""
    log_path = _resolve_log_path(path)
    try:
        if log_path.exists():
            log_path.unlink()
    except OSError:
        # Ignore removal errors to avoid blocking the orchestrator.
        pass


def log_stage_transition(
    stage: str,
    status: str,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    level: str = "info",
) -> Dict[str, Any]:
    """Record a pipeline stage transition."""

    details: Dict[str, Any] = {"stage": stage, "status": status}
    if metadata:
        details.update(metadata)
    return append_event(
        level=level,
        source="pipeline",
        message="stage_transition",
        details=details,
    )


def log_token_usage(
    stage: str,
    *,
    usage: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record token usage for a stage."""

    details: Dict[str, Any] = {"stage": stage}
    if usage:
        details.update({k: v for k, v in usage.items() if k in {"input_tokens", "output_tokens", "total_tokens"}})
    return append_event(
        level="info",
        source="pipeline",
        message="token_usage",
        details=details,
    )


def log_quota_snapshot(
    stage: str,
    *,
    usage: Optional[Dict[str, Any]] = None,
    limits: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Record a snapshot of account usage and rate-limit metadata."""

    if not (usage or limits):
        return None

    details: Dict[str, Any] = {"stage": stage}
    if usage:
        details["usage"] = usage
    if limits:
        details["limits"] = limits

    return append_event(
        level="info",
        source="pipeline",
        message="openai_quota",
        details=details,
    )
