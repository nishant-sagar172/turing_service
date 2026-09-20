"""Unit tests for the client correlation ref, v2 execution paging and the
variable contract. Pure functions and a stubbed transport only — no database.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.variables import SYSTEM_VARIABLES, resolve_agent_variables
from app.core.voice_engine import VoiceEngineClient
from app.services.store import extract_client_ref, extract_patient_ref
from app.services.variables import check


def _recipient_payload(**data: Any) -> dict[str, Any]:
    return {"context_details": {"recipient_data": data}}


def test_client_ref_is_read_from_the_recipient_row() -> None:
    payload = _recipient_payload(patient_uhid="UH-1", client_ref="row-42")
    assert extract_client_ref(payload) == "row-42"
    assert extract_patient_ref(payload) == "UH-1"


def test_client_ref_is_none_when_the_row_omits_it() -> None:
    assert extract_client_ref(_recipient_payload(patient_uhid="UH-1")) is None
    assert extract_client_ref({}) is None
    assert extract_client_ref({"context_details": None}) is None


def test_client_ref_is_stringified() -> None:
    assert extract_client_ref(_recipient_payload(client_ref=42)) == "42"


def test_system_variables_match_the_voice_engine_list() -> None:
    """The engine injects exactly these eight; contact_number is not among them,
    it is a CSV column the caller supplies."""
    assert SYSTEM_VARIABLES == frozenset(
        {
            "agent_id",
            "execution_id",
            "call_sid",
            "from_number",
            "to_number",
            "current_date",
            "current_time",
            "timezone",
        }
    )


def test_contact_number_stays_a_required_prompt_variable() -> None:
    """Every CSV column maps to a prompt variable, contact_number included, so
    a prompt may reference it and the contract must still list it."""
    agent = {
        "agent_prompts": {"task_1": {"system_prompt": "Hi {name} on {contact_number}"}}
    }

    contract = resolve_agent_variables(agent)

    assert contract["required"] == ["contact_number", "name"]


def test_a_recipient_satisfies_a_prompt_that_uses_contact_number() -> None:
    """The phone column is provided, so the batch pre-check must not report it
    missing — doing so made such an agent reject every recipient."""
    contract = {"required": ["contact_number", "name"], "optional": []}

    missing, _ = check({"contact_number", "name"}, contract)

    assert missing == []


class _StubTransport:
    """Returns one canned response per request, recording the params sent."""

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages
        self.calls: list[dict[str, Any]] = []

    async def request(self, _method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append({"path": path, "params": kwargs.get("params")})
        return self._pages[len(self.calls) - 1]


def _client_with(
    pages: list[dict[str, Any]],
) -> tuple[VoiceEngineClient, _StubTransport]:
    client = VoiceEngineClient.__new__(VoiceEngineClient)
    stub = _StubTransport(pages)
    client.request = stub.request  # type: ignore[method-assign]
    return client, stub


@pytest.mark.asyncio
async def test_executions_follow_every_page() -> None:
    client, stub = _client_with(
        [
            {"data": [{"id": "a"}, {"id": "b"}], "has_more": True},
            {"data": [{"id": "c"}], "has_more": False},
        ]
    )

    items = await client.get_batch_executions("batch-1")

    assert [item["id"] for item in items] == ["a", "b", "c"]
    assert [call["path"] for call in stub.calls] == [
        "/v2/batches/batch-1/executions"
    ] * 2
    assert [call["params"]["page_number"] for call in stub.calls] == [1, 2]


@pytest.mark.asyncio
async def test_executions_stop_on_the_first_page_when_there_is_no_more() -> None:
    client, stub = _client_with([{"data": [{"id": "a"}], "has_more": False}])

    items = await client.get_batch_executions("batch-1")

    assert [item["id"] for item in items] == ["a"]
    assert len(stub.calls) == 1


@pytest.mark.asyncio
async def test_a_bare_array_body_is_passed_straight_through() -> None:
    """Falls back to the v1 shape rather than returning nothing."""
    client, _ = _client_with([[{"id": "a"}]])

    assert await client.get_batch_executions("batch-1") == [{"id": "a"}]


@pytest.mark.asyncio
async def test_unexpected_dict_shape_warns_instead_of_silent_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, stub = _client_with([{"error": "boom"}])

    with caplog.at_level("WARNING"):
        items = await client.get_batch_executions("batch-1")

    assert items == []
    assert len(stub.calls) == 1
    assert any("unexpected response shape" in r.message for r in caplog.records)
