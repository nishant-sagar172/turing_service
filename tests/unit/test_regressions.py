"""Regression tests: desired POST-FIX behaviour for known findings.

Each test below is a genuine, correct assertion of what the code *should* do.
They are expected to FAIL against the current, unfixed code — hence
``xfail(strict=False)``. When the corresponding fix lands elsewhere in this
review wave, these should flip to XPASS with no changes needed here.

Do not use ``strict=True``: these are safety nets for work-in-progress fixes,
not enforcement that a fix landed on a particular day.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from app.core.variables import load_variable_overrides
from app.core.voice_engine import VoiceEngineClient
from app.services import rate_limit
from app.services.store import _call_fields_from_execution

# ---------------------------------------------------------------------------
# B-3: cost mapping must not raise on a non-numeric total_cost, and must not
# silently treat a bool as a number.
# ---------------------------------------------------------------------------


def test_cost_is_none_not_raise_for_string_total_cost() -> None:
    fields = _call_fields_from_execution({"total_cost": "12.5"})
    assert fields["cost"] is None


def test_cost_is_none_for_bool_total_cost() -> None:
    # bool is a subclass of int in Python; True / 100 == 0.01 today, which is
    # a bogus cost that must never be stored.
    fields = _call_fields_from_execution({"total_cost": True})
    assert fields["cost"] is None


# ---------------------------------------------------------------------------
# B-4: schedule_batch's multipart form serialization must render booleans as
# lowercase JSON-style strings and dict/list values as JSON, not repr().
# ---------------------------------------------------------------------------


def test_schedule_batch_serializes_bool_and_json_values_correctly() -> None:
    captured: dict[str, Any] = {}

    async def fake_request(*_args: Any, **kwargs: Any) -> Any:
        captured["files"] = kwargs.get("files")
        return {}

    # base_url is a required parameter (B-14: Settings is the single source of
    # truth for the vendor URL, so the client no longer carries a default).
    client = VoiceEngineClient(api_key="test-key", base_url="https://example.invalid")
    client.request = fake_request  # type: ignore[method-assign]

    asyncio.run(
        client.schedule_batch(
            "batch-1",
            {"is_recurring": True, "meta": {"a": 1}, "tags": [1, 2]},
        )
    )

    files = captured["files"]
    assert files["is_recurring"] == (None, "true")
    assert files["meta"] == (None, '{"a": 1}')
    assert files["tags"] == (None, "[1, 2]")


# ---------------------------------------------------------------------------
# B-7: load_variable_overrides must reflect a file edit without a process
# restart. Currently defeated by @lru_cache keyed on the path string.
# ---------------------------------------------------------------------------


def test_load_variable_overrides_reflects_file_edit_without_restart(
    tmp_path: Path,
) -> None:
    load_variable_overrides.cache_clear()
    path = tmp_path / "overrides.json"

    path.write_text('{"agent-1": {"optional": ["nickname"]}}', encoding="utf-8")
    first = load_variable_overrides(str(path))
    assert first == {"agent-1": {"optional": ["nickname"]}}

    path.write_text('{"agent-1": {"optional": ["age"]}}', encoding="utf-8")
    second = load_variable_overrides(str(path))

    assert second == {"agent-1": {"optional": ["age"]}}


# ---------------------------------------------------------------------------
# B-8: the in-memory rate-limit fallback must not retain a bucket key once
# its window has fully expired — otherwise the dict grows without bound as
# new source IPs hit an open endpoint like POST /v1/register.
# ---------------------------------------------------------------------------


def test_memory_rate_limit_drops_expired_bucket_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rate_limit._attempts.clear()
    real_monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: real_monotonic())

    rate_limit._memory_hit(bucket="1.2.3.4", limit=3, window_seconds=60)
    assert "1.2.3.4" in rate_limit._attempts

    # Advance well past the window, then hit a *different* bucket — a bucket
    # whose window has fully lapsed and is never touched again must not sit
    # in the dict forever.
    monkeypatch.setattr(time, "monotonic", lambda: real_monotonic() + 1000)
    rate_limit._memory_hit(bucket="5.6.7.8", limit=3, window_seconds=60)

    assert "1.2.3.4" not in rate_limit._attempts
