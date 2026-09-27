"""End-to-end analysis flow with stubbed LLM clients and session — no database,
no network: transcript -> analyze_call -> CallAnalysis -> client webhook payload.
"""

from __future__ import annotations

import json
import types
import uuid
from typing import Any, cast

import pytest

from app.config import Settings
from app.db.models import Call, CallAnalysis
from app.services import analysis as analysis_service
from app.services.outcome_notifier import build_outcome

TRANSCRIPT = (
    "assistant: क्या आप 10 September को appointment लेना चाहेंगे?\n"
    "user: यह one thing मैं उनसे verify करूंगा, मैं call करूंगा।"
)

LLM_RESULT: dict[str, Any] = {
    "reason": "Son actively deferred the booking to verify and call back.",
    "call_outcome": "follow_up",
    "summary": (
        "Offered a 10 September appointment, the patient's son deferred, saying "
        "he will verify and call back. No booking made; awaiting his callback."
    ),
    "requests": [],
    "urgency": "low",
    "confidence": 0.9,
    "symptoms_reported": [],
}


class _FakeResult:
    def scalar_one_or_none(self) -> None:
        return None


class _FakeSession:
    """Behaves as if no batch row and no prior analysis exist."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    async def execute(self, _statement: Any) -> _FakeResult:
        return _FakeResult()

    def add(self, row: Any) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        return None


class _FakeAnthropicMessages:
    def __init__(self, tool_input: dict[str, Any], stop_reason: str) -> None:
        self._tool_input = tool_input
        self._stop_reason = stop_reason
        self.sent: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.sent = kwargs
        block = types.SimpleNamespace(
            type="tool_use", name="classify_call", input=self._tool_input
        )
        return types.SimpleNamespace(content=[block], stop_reason=self._stop_reason)


class _FakeOpenAICompletions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.sent: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.sent = kwargs
        message = types.SimpleNamespace(content=self._content, refusal=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def _settings(provider: str) -> Settings:
    return cast(
        Settings,
        types.SimpleNamespace(
            llm_provider=provider,
            llm_model=None,
            anthropic_api_key="test-anthropic-key",
            openai_api_key="test-openai-key",
            encryption_key=None,
        ),
    )


def _call() -> Call:
    return Call(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        agent_id="agent-1",
        batch_id=None,
        workflow_code=None,
        voice_call_id="exec-1",
        contact_number="+919999999999",
        from_number="+918888888888",
        status="completed",
        transcript=TRANSCRIPT,
    )


def _stub_anthropic(
    monkeypatch: pytest.MonkeyPatch,
    tool_input: dict[str, Any],
    stop_reason: str = "tool_use",
) -> _FakeAnthropicMessages:
    messages = _FakeAnthropicMessages(tool_input, stop_reason)
    client = types.SimpleNamespace(messages=messages)
    monkeypatch.setattr(analysis_service, "_get_anthropic_client", lambda _key: client)
    return messages


def _stub_openai(
    monkeypatch: pytest.MonkeyPatch, content: str
) -> _FakeOpenAICompletions:
    completions = _FakeOpenAICompletions(content)
    client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=completions))
    monkeypatch.setattr(analysis_service, "_get_openai_client", lambda _key: client)
    return completions


def test_tool_schema_is_strict_and_reasons_before_labelling() -> None:
    schema = analysis_service._build_tool_schema(None)

    assert schema["strict"] is True
    assert schema["input_schema"]["additionalProperties"] is False
    properties = list(schema["input_schema"]["properties"])
    assert properties.index("reason") < properties.index("call_outcome")
    assert set(schema["input_schema"]["required"]) == set(properties)


def test_system_prompt_asks_for_crux_first_summary() -> None:
    prompt = analysis_service._build_system_prompt(None)

    assert "crux first" in prompt
    assert "decision point" in prompt
    assert prompt.count("→ summary:") == 3


@pytest.mark.asyncio
async def test_anthropic_flow_persists_analysis_and_reaches_the_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = _stub_anthropic(monkeypatch, LLM_RESULT)
    session = _FakeSession()
    call = _call()

    analysis = await analysis_service.analyze_call(
        session,  # type: ignore[arg-type]
        call,
        _settings("anthropic"),
    )

    assert analysis is not None
    assert session.added == [analysis]
    assert messages.sent["tool_choice"] == {"type": "tool", "name": "classify_call"}
    assert messages.sent["tools"][0]["strict"] is True
    assert analysis.call_outcome == "follow_up"
    assert analysis.summary == LLM_RESULT["summary"]
    assert analysis.reason == LLM_RESULT["reason"]
    assert analysis.urgency == "low"
    assert str(analysis.model_used).startswith("anthropic/")

    payload = build_outcome(call, None, analysis)

    block = payload["analysis"]
    assert block["summary"] == LLM_RESULT["summary"]
    assert block["reason"] == LLM_RESULT["reason"]
    assert block["requests"] == []
    assert block["urgency"] == "low"
    assert block["confidence"] == 0.9
    assert block["call_outcome"] == "follow_up"
    assert payload["transcript"] == TRANSCRIPT


@pytest.mark.asyncio
async def test_openai_flow_sends_strict_schema_in_reason_first_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completions = _stub_openai(monkeypatch, json.dumps(LLM_RESULT))
    call = _call()

    analysis = await analysis_service.analyze_call(
        _FakeSession(),  # type: ignore[arg-type]
        call,
        _settings("openai"),
    )

    assert analysis is not None
    json_schema = completions.sent["response_format"]["json_schema"]
    assert json_schema["strict"] is True
    assert list(json_schema["schema"]["properties"])[0] == "reason"
    assert analysis.summary == LLM_RESULT["summary"]
    assert (
        build_outcome(call, None, analysis)["analysis"]["reason"]
        == (LLM_RESULT["reason"])
    )


@pytest.mark.asyncio
async def test_unknown_outcome_fails_safe_to_escalation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_anthropic(monkeypatch, {**LLM_RESULT, "call_outcome": "not_a_real_outcome"})

    analysis = await analysis_service.analyze_call(
        _FakeSession(),  # type: ignore[arg-type]
        _call(),
        _settings("anthropic"),
    )

    assert analysis is not None
    assert analysis.call_outcome == "escalation"


@pytest.mark.asyncio
async def test_truncated_anthropic_response_records_no_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_anthropic(monkeypatch, {"reason": "cut"}, stop_reason="max_tokens")
    session = _FakeSession()

    analysis = await analysis_service.analyze_call(
        session,  # type: ignore[arg-type]
        _call(),
        _settings("anthropic"),
    )

    assert analysis is None
    assert session.added == []


def test_status_only_call_gets_placeholder_analysis_in_the_webhook() -> None:
    analysis = CallAnalysis(
        call_outcome="no_output",
        summary="Call ended with status: no-answer",
        reason="Auto-classified from terminal status 'no-answer' (no transcript).",
        requests=[],
        model_used=analysis_service.STATUS_CLASSIFIER_MODEL,
    )

    block = build_outcome(_call(), None, analysis)["analysis"]

    assert block["summary"] == "Call ended with status: no-answer"
    assert block["urgency"] is None
    assert block["requests"] == []
