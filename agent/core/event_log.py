"""Persistent event log utilities for orchestrator runs."""
from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

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


def clear_events(path: Optional[pathlib.Path] = None) -> None:
    """Remove all stored events."""
    log_path = _resolve_log_path(path)
    try:
        if log_path.exists():
            log_path.unlink()
    except OSError:
        # Ignore removal errors to avoid blocking the orchestrator.
        pass
