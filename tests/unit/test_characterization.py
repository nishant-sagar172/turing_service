"""Characterization tests: pin down behaviour that must NOT change.

These tests describe the codebase as it exists today, warts and all. If one
of these fails, the test is wrong (or was written against a misreading of
the code) — investigate and fix the *test*, never "fix" app code to make a
characterization test pass.

Scope: pure functions/constants only. No database session is created here
(app/db/models.py uses Postgres-only JSONB/UUID types, so SQLite is not an
option and these tests must not touch a real Postgres instance either).
"""

from __future__ import annotations

import json
import types
from pathlib import Path
from typing import cast

from app.core.call_status import normalize_batch_status
from app.core.variables import load_variable_overrides
from app.db.models import CallAnalysis
from app.routers.calls import _analysis_result
from app.routers.webhooks import BATCH_TERMINAL_STATUSES
from app.services import store
from app.services.analytics import CONNECTED, NOT_CONNECTED, TERMINAL

# ---------------------------------------------------------------------------
# app/services/store.py — call-level terminal/success status sets
# ---------------------------------------------------------------------------


def test_success_statuses_is_exactly_completed() -> None:
    assert store._SUCCESS_STATUSES == {"completed"}


def test_terminal_statuses_is_exactly_the_nine_known_values() -> None:
    expected = {
        "completed",
        "no-answer",
        "busy",
        "failed",
        "canceled",
        "cancelled",
        "stopped",
        "error",
        "balance-low",
    }
    assert store.TERMINAL_STATUSES == expected
    assert len(store.TERMINAL_STATUSES) == 9
    for status in expected:
        assert status in store.TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# app/services/analytics.py — CONNECTED / NOT_CONNECTED / TERMINAL
# ---------------------------------------------------------------------------


def test_connected_is_exactly_completed() -> None:
    assert CONNECTED == frozenset({"completed"})


def test_not_connected_is_exactly_the_eight_known_values() -> None:
    expected = frozenset(
        {
            "no-answer",
            "busy",
            "failed",
            "canceled",
            "cancelled",
            "stopped",
            "error",
            "balance-low",
        }
    )
    assert NOT_CONNECTED == expected


def test_terminal_equals_connected_union_not_connected() -> None:
    assert TERMINAL == CONNECTED | NOT_CONNECTED


def test_analytics_terminal_matches_store_terminal_statuses() -> None:
    assert TERMINAL == store.TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# app/routers/webhooks.py — batch-level terminal statuses (a THIRD, distinct
# set from the call-level ones above)
# ---------------------------------------------------------------------------


def test_batch_terminal_statuses_is_exactly_the_five_known_values() -> None:
    expected = frozenset({"completed", "stopped", "failed", "cancelled", "canceled"})
    assert BATCH_TERMINAL_STATUSES == expected


# ---------------------------------------------------------------------------
# app/core/variables.py — load_variable_overrides
# ---------------------------------------------------------------------------


def test_load_variable_overrides_missing_path_returns_empty_dict() -> None:
    load_variable_overrides.cache_clear()
    assert load_variable_overrides("Z:/does/not/exist/overrides.json") == {}


def test_load_variable_overrides_parses_real_file(tmp_path: Path) -> None:
    load_variable_overrides.cache_clear()
    path = tmp_path / "overrides.json"
    path.write_text(
        json.dumps({"agent-1": {"optional": ["nickname"]}}), encoding="utf-8"
    )

    result = load_variable_overrides(str(path))

    assert result == {"agent-1": {"optional": ["nickname"]}}


def test_load_variable_overrides_malformed_json_returns_empty_dict(
    tmp_path: Path,
) -> None:
    load_variable_overrides.cache_clear()
    path = tmp_path / "broken.json"
    path.write_text("{not valid json", encoding="utf-8")

    assert load_variable_overrides(str(path)) == {}


# ---------------------------------------------------------------------------
# app/services/store.py — _call_fields_from_execution mapping
# ---------------------------------------------------------------------------


def test_call_fields_from_execution_maps_well_formed_payload() -> None:
    payload = {
        "status": "completed",
        "transcript": "hello",
        "telephony_data": {
            "recording_url": "http://example.com/rec.mp3",
            "duration": 45,
            "hangup_reason": "user_hangup",
            "to_number": "+911234567890",
        },
        "extracted_data": {"foo": "bar"},
        "total_cost": 250,
        "conversation_duration": 42,
        "batch_run_details": {"retry_count": 2, "batch_id": "b1"},
    }

    fields = store._call_fields_from_execution(payload)

    assert fields == {
        "status": "completed",
        "transcript": "hello",
        "recording_url": "http://example.com/rec.mp3",
        "extracted_data": {"foo": "bar"},
        "cost": 2.5,
        # B-10 deliberately added this field: integer minor units are dual-written
        # alongside the legacy float so analytics can migrate off binary-float
        # money. `cost` is unchanged, so no API response shape changed.
        "cost_cents": 250,
        "duration": 42,
        "hangup_reason": "user_hangup",
        "retry_count": 2,
        "raw_payload": payload,
    }


# ---------------------------------------------------------------------------
# app/schemas/analysis.py CallAnalysisResult, via app.routers.calls._analysis_result
# ---------------------------------------------------------------------------


def test_analysis_result_maps_none_requests_and_symptoms_to_empty_lists() -> None:
    # What analyze_call writes: one granular `call_outcome`, with the
    # disposition pair derived from it in Python.
    fake_analysis = types.SimpleNamespace(
        call_outcome="scheduled_booking",
        disposition_status="Booking",
        sub_status=None,
        workflow_code="opd",
        summary="Patient confirmed appointment.",
        reason="Explicit confirmation of slot.",
        requests=None,
        urgency="low",
        confidence=0.9,
        symptoms_reported=None,
        model_used="openai/gpt-5.6-luna",
        analyzed_at=None,
    )

    result = _analysis_result(cast(CallAnalysis, fake_analysis))

    assert result is not None
    assert result.call_outcome == "scheduled_booking"
    assert result.disposition_status == "Booking"
    assert result.sub_status is None
    assert result.workflow_code == "opd"
    assert result.summary == "Patient confirmed appointment."
    assert result.reason == "Explicit confirmation of slot."
    assert result.requests == []
    assert result.urgency == "low"
    assert result.confidence == 0.9
    assert result.symptoms_reported == []
    assert result.model_used == "openai/gpt-5.6-luna"
    assert result.analyzed_at is None


def test_analysis_result_passes_through_pre_disposition_rows() -> None:
    """Rows analysed before 0009 have no classification at all after 0011.

    0011 dropped the `outcome` mirror without backfilling, so these rows carry
    NULL everywhere. The serializer must surface them as unclassified rather
    than erroring or inventing a disposition.
    """
    legacy_analysis = types.SimpleNamespace(
        call_outcome=None,
        disposition_status=None,
        sub_status=None,
        workflow_code=None,
        summary="Call ended with status: no-answer",
        reason="Auto-classified from terminal status 'no-answer' (no transcript).",
        requests=[],
        urgency=None,
        confidence=None,
        symptoms_reported=None,
        model_used="status-classifier/v1",
        analyzed_at=None,
    )

    result = _analysis_result(cast(CallAnalysis, legacy_analysis))

    assert result is not None
    assert result.call_outcome is None
    assert result.disposition_status is None
    assert result.sub_status is None
    assert result.workflow_code is None


def test_analysis_result_returns_none_for_none_analysis() -> None:
    assert _analysis_result(None) is None


# ---------------------------------------------------------------------------
# app/core/call_status.py — normalize_batch_status
# ---------------------------------------------------------------------------


def test_normalize_batch_status_strips_the_glued_on_schedule() -> None:
    # Bolna reports a scheduled batch with the timestamp inside the status.
    assert normalize_batch_status("scheduled at 2026-09-15T14:16:00.000+00:00") == (
        "scheduled"
    )
    assert normalize_batch_status("scheduled at 2026-08-28T19:32:00+05:30") == (
        "scheduled"
    )


def test_normalize_batch_status_leaves_plain_statuses_alone() -> None:
    for status in BATCH_TERMINAL_STATUSES | {"scheduled", "running"}:
        assert normalize_batch_status(status) == status


def test_normalize_batch_status_maps_empty_to_none() -> None:
    assert normalize_batch_status(None) is None
    assert normalize_batch_status("") is None
    assert normalize_batch_status("   ") is None


def test_every_batch_status_write_goes_through_the_normalizer() -> None:
    """The engine glues a timestamp onto 'scheduled'; one unguarded write path
    is enough to put it back in the column, which is how 14 rows got there."""
    # Flag a status taken straight from the engine rather than the variable it
    # was already normalised into.
    engine_sourced = ("response.state", 'live["status"]', 'live.get("status")')
    raw_writes = [
        line.strip()
        for path in ("app/routers/batches.py", "app/routers/webhooks.py")
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if any(src in line for src in engine_sourced)
        and "normalize_batch_status" not in line
    ]
    assert raw_writes == [], f"unnormalised batch status writes: {raw_writes}"


# ---------------------------------------------------------------------------
# app/routers/health.py — readiness must distinguish itself from liveness
# ---------------------------------------------------------------------------


def test_readiness_returns_503_naming_the_failed_dependency() -> None:
    """A dead database must not read as a generic 500 with no detail, and must
    not leave container healthchecks reporting green."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.routers import health as health_router

    def exploding_factory():  # type: ignore[no-untyped-def]
        raise ConnectionRefusedError("connection refused")

    original = health_router.get_session_factory
    health_router.get_session_factory = exploding_factory
    try:
        client = TestClient(create_app(), raise_server_exceptions=False)
        response = client.get("/health/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["detail"]["error"] == "database_unreachable"
        assert body["detail"]["cause"] == "ConnectionRefusedError"
        # Liveness stays up — the process is fine, its dependency is not.
        assert client.get("/health").status_code == 200
    finally:
        health_router.get_session_factory = original


def test_container_healthchecks_probe_readiness_not_liveness() -> None:
    for path in ("Dockerfile", "docker-compose.yml", "docker-compose.prod.yml"):
        text = Path(path).read_text(encoding="utf-8")
        assert "8005/health/ready" in text, f"{path} does not probe readiness"
        assert '8005/health"' not in text and "8005/health " not in text, (
            f"{path} still probes bare /health"
        )
