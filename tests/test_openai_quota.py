from __future__ import annotations

import json

from agent.core.openai_quota import (
    QuotaSnapshot,
    format_quota_snapshot_for_console,
)


def test_format_quota_snapshot_for_console_returns_serialised_payload() -> None:
    snapshot = QuotaSnapshot(
        usage={"totals": {"requests": 12, "tokens": 345}},
        limits={"limits": [{"name": "requests", "metrics": {"limit": 100}}]},
    )

    rendered = format_quota_snapshot_for_console("context_summary", snapshot)

    assert rendered is not None
    prefix, payload = rendered.split(" ", 1)
    assert prefix == "[quota:context_summary]"
    data = json.loads(payload)
    assert data["usage"]["totals"]["requests"] == 12
    assert data["limits"]["limits"][0]["metrics"]["limit"] == 100


def test_format_quota_snapshot_for_console_handles_blank_stage() -> None:
    snapshot = QuotaSnapshot(usage={"totals": {"requests": 1}})

    rendered = format_quota_snapshot_for_console("", snapshot)

    assert rendered is not None
    assert rendered.startswith("[quota:unknown] ")


def test_format_quota_snapshot_for_console_ignores_empty_snapshot() -> None:
    snapshot = QuotaSnapshot()

    assert format_quota_snapshot_for_console("context_summary", snapshot) is None
