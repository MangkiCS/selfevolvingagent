from __future__ import annotations

import json

from agent.core import event_log


def test_append_and_load_events(tmp_path, monkeypatch):
    log_path = tmp_path / "log.json"
    monkeypatch.setenv("AGENT_EVENT_LOG_PATH", str(log_path))
    event_log.clear_events()

    stored = event_log.append_event(
        level="error",
        source="unit_test",
        message="Something failed",
        details={"code": 123},
    )
    assert stored["level"] == "error"
    assert stored["message"] == "Something failed"

    events = event_log.load_events()
    assert len(events) == 1
    assert events[0]["source"] == "unit_test"
    assert events[0]["details"] == {"code": 123}

    # Ensure the file is valid JSON for downstream consumers.
    raw = log_path.read_text(encoding="utf-8")
    loaded = json.loads(raw)
    assert isinstance(loaded, list)


def test_event_log_truncates_to_max(tmp_path, monkeypatch):
    log_path = tmp_path / "log.json"
    monkeypatch.setenv("AGENT_EVENT_LOG_PATH", str(log_path))
    event_log.clear_events()

    for idx in range(event_log.MAX_EVENTS + 5):
        event_log.append_event(level="error", source="s", message=f"m{idx}")

    events = event_log.load_events()
    assert len(events) == event_log.MAX_EVENTS
    assert events[0]["message"] == "m5"
    assert events[-1]["message"] == f"m{event_log.MAX_EVENTS + 4}"
