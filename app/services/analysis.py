"""LLM-based call outcome classification.

Resolution order for provider / model / API key:
  1. client_config.analysis_llm_* (per-client override)
  2. Settings.llm_* (system env vars)
  3. Skip — log warning, return None without crashing the caller.

Anthropic path uses tool_use to enforce structured JSON output.
OpenAI path uses response_format=json_object with an explicit JSON schema
description in the prompt.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

# Retry budget for transient LLM provider failures.
_MAX_ANALYSIS_ATTEMPTS = 3
_ANALYSIS_BACKOFF_S = 1.0


def _is_retryable(exc: Exception) -> bool:
    """Whether an LLM provider error is worth another attempt.

    Both provider SDKs are imported lazily inside their call helpers, so their
    exception classes are matched structurally rather than by import: a 429 or
    5xx is transient, any other 4xx (bad key, malformed request) is permanent
    and must fail fast.
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    # Connection/timeout failures carry no status code.
    return type(exc).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "APIConnectionTimeoutError",
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "TimeoutException",
    }


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.encryption import EncryptionError, decrypt
from app.db.models import Call, CallAnalysis, ClientConfig

logger = logging.getLogger("turing.analysis")

OUTCOME_BUCKETS = frozenset(
    {"booking", "escalation", "not_interested", "no_output", "follow_up", "other"}
)
URGENCY_LEVELS = frozenset({"low", "medium", "high"})

_DEFAULT_MODELS = {"anthropic": "claude-haiku-4-5-20251001", "openai": "gpt-4o-mini"}

_SYSTEM_PROMPT = """\
You are a call outcome classifier for an outbound patient healthcare voice service \
(follow-ups, appointment reminders, check-ins). Transcripts may be Hindi, English, \
or Hinglish, with disfluencies or transcription noise — judge by intent, not exact \
wording. Read the full transcript; the outcome often depends on how it ends.

Classify into exactly ONE bucket. If more than one applies, resolve by priority \
(patient safety outranks scheduling): escalation > booking > follow_up > \
not_interested > no_output > other.

- booking: patient explicitly confirms a specific appointment/procedure/callback \
  (a date/time, or "yes" to a proposed slot). Not a slot left unconfirmed, or a \
  soft "I'll try"/"maybe".

- escalation: any acute/worsening symptom (chest pain, breathlessness, \
  uncontrolled bleeding, high fever, severe pain, fainting, seizures, post-op \
  complication, adverse drug reaction), self-harm/suicidal mention, explicit \
  urgent-callback request, or a vulnerable situation (confused patient, \
  non-adherence, treatment not working). Still fill urgency/requests/\
  symptoms_reported normally. A later booking in the same call does not override \
  this.

- follow_up: patient undecided, unavailable, or asks to be contacted again with \
  no refusal — "call later", "checking with family/doctor", call cut short, \
  wants more time/info. Non-committal is not not_interested.

- not_interested: explicit, unambiguous decline — "not interested", "don't call \
  again", "remove my number". A curt tone alone is not a decline.

- no_output: call connected but no real patient interaction — wrong number, \
  voicemail/IVR, immediate hangup, third party couldn't relay anything, dead air, \
  unintelligible transcript.

- other: last resort — coherent, engaged call that fits nothing above. Not a \
  default for uncertainty.

Also assess for every call:
- urgency (low/medium/high): how urgently a human should review this call.
- confidence (0.0-1.0): lower for unclear audio, code-switching, or ambiguity.
- symptoms_reported: any symptom/complaint mentioned, in any bucket — not just \
  escalation.
"""

_TOOL_SCHEMA: Any = {
    "name": "classify_call",
    "description": "Classify a call outcome and generate structured analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "outcome": {
                "type": "string",
                "enum": sorted(OUTCOME_BUCKETS),
            },
            "summary": {
                "type": "string",
                "description": "2-3 sentence plain-language summary of the call.",
            },
            "reason": {
                "type": "string",
                "description": "Why this outcome was assigned.",
            },
            "requests": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Concrete asks or requests made during the call.",
            },
            "urgency": {
                "type": "string",
                "enum": sorted(URGENCY_LEVELS),
                "description": "How urgently this call needs human follow-up.",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in this classification, from 0.0 to 1.0.",
            },
            "symptoms_reported": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Symptoms or health issues the patient mentioned, if any.",
            },
        },
        "required": [
            "outcome",
            "summary",
            "reason",
            "requests",
            "urgency",
            "confidence",
            "symptoms_reported",
        ],
    },
}


def _resolve_provider_model(
    settings: Settings, config: ClientConfig | None
) -> tuple[str, str]:
    provider = (
        (config.analysis_llm_provider if config else None)
        or settings.llm_provider
        or "anthropic"
    )
    model = (
        (config.analysis_llm_model if config else None)
        or settings.llm_model
        or _DEFAULT_MODELS.get(provider, "claude-haiku-4-5-20251001")
    )
    return provider, model


def _resolve_api_key(
    settings: Settings, config: ClientConfig | None, provider: str
) -> str | None:
    if config and config.analysis_llm_api_key_enc and settings.encryption_key:
        try:
            return decrypt(config.analysis_llm_api_key_enc, settings.encryption_key)
        except EncryptionError:
            logger.warning(
                "Failed to decrypt per-client LLM API key; falling back to system key"
            )
    return (
        settings.anthropic_api_key
        if provider == "anthropic"
        else settings.openai_api_key
    )


def _build_user_content(call: Call) -> str:
    parts = [f"TRANSCRIPT:\n{call.transcript}"]
    if call.extracted_data:
        parts.append(f"EXTRACTED DATA:\n{json.dumps(call.extracted_data, indent=2)}")
    return "\n\n".join(parts)


async def _call_anthropic(
    api_key: str, model: str, system: str, user_content: str
) -> dict[str, Any]:
    import anthropic  # lazy import — only loaded if provider is anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "classify_call"},
        messages=[{"role": "user", "content": user_content}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "classify_call":
            return dict(block.input)
    raise ValueError("No classify_call tool_use block in Anthropic response")


async def _call_openai(
    api_key: str, model: str, system: str, user_content: str
) -> dict[str, Any]:
    import openai  # lazy import — only loaded if provider is openai

    client = openai.AsyncOpenAI(api_key=api_key)
    schema_desc = (
        "Respond with a JSON object containing exactly these keys: "
        "outcome (one of: booking, escalation, not_interested, no_output, follow_up, other), "
        "summary (2-3 sentences), reason (string), requests (array of strings), "
        "urgency (one of: low, medium, high), confidence (number 0.0-1.0), "
        "symptoms_reported (array of strings)."
    )
    response = await client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": f"{system}\n\n{schema_desc}"},
            {"role": "user", "content": user_content},
        ],
    )
    return json.loads(response.choices[0].message.content or "{}")


async def analyze_call(
    session: AsyncSession,
    call: Call,
    settings: Settings,
    client_config: ClientConfig | None = None,
) -> CallAnalysis | None:
    """Classify a call via LLM and upsert the result into call_analysis.

    Returns None (without raising) when the call has no transcript, no API
    key is available, or the LLM call fails — the call record is always safe.
    """
    if not call.transcript:
        logger.debug("Skipping analysis for call %s — no transcript", call.id)
        return None

    provider, model = _resolve_provider_model(settings, client_config)
    api_key = _resolve_api_key(settings, client_config, provider)
    if not api_key:
        logger.warning(
            "No LLM API key available (provider=%s) for call %s — skipping analysis",
            provider,
            call.id,
        )
        return None

    system = _SYSTEM_PROMPT
    if client_config and client_config.analysis_prompt_hint:
        system += f"\n\nClient context: {client_config.analysis_prompt_hint}"

    user_content = _build_user_content(call)

    # Bounded retry: analysis runs exactly once per terminal transition and
    # nothing re-triggers it, so swallowing a transient rate-limit or 5xx left
    # the call permanently unanalysed — on a healthcare classifier that flags
    # escalations, silently losing exactly the calls that hit a blip.
    result: dict[str, Any] | None = None
    for attempt in range(_MAX_ANALYSIS_ATTEMPTS):
        try:
            if provider == "anthropic":
                result = await _call_anthropic(api_key, model, system, user_content)
            else:
                result = await _call_openai(api_key, model, system, user_content)
            break
        except Exception as exc:
            is_last = attempt + 1 >= _MAX_ANALYSIS_ATTEMPTS
            if not _is_retryable(exc) or is_last:
                logger.exception(
                    "LLM analysis failed for call %s (attempt %d/%d, retryable=%s)",
                    call.id,
                    attempt + 1,
                    _MAX_ANALYSIS_ATTEMPTS,
                    _is_retryable(exc),
                )
                return None
            logger.warning(
                "LLM analysis attempt %d/%d for call %s failed (%s); retrying",
                attempt + 1,
                _MAX_ANALYSIS_ATTEMPTS,
                call.id,
                type(exc).__name__,
            )
            await asyncio.sleep(_ANALYSIS_BACKOFF_S * (2**attempt))

    if result is None:  # defensive: loop always breaks or returns
        return None

    outcome = result.get("outcome", "other")
    if outcome not in OUTCOME_BUCKETS:
        outcome = "other"

    now = datetime.now(timezone.utc)
    model_tag = f"{provider}/{model}"

    existing = await session.execute(
        select(CallAnalysis).where(CallAnalysis.call_id == call.id)
    )
    analysis = existing.scalar_one_or_none()

    if analysis is None:
        analysis = CallAnalysis(
            call_id=call.id,
            client_id=call.client_id,
            agent_id=call.agent_id,
            batch_id=call.batch_id,
        )
        session.add(analysis)

    urgency = result.get("urgency")
    confidence = result.get("confidence")

    analysis.outcome = outcome
    analysis.summary = result.get("summary") or ""
    analysis.reason = result.get("reason") or ""
    analysis.requests = result.get("requests") or []
    analysis.urgency = urgency if urgency in URGENCY_LEVELS else None
    analysis.confidence = (
        float(confidence) if isinstance(confidence, (int, float)) else None
    )
    analysis.symptoms_reported = result.get("symptoms_reported") or []
    analysis.model_used = model_tag
    analysis.analyzed_at = now
    analysis.raw_llm_response = result

    await session.flush()
    logger.info("Call %s analysed: outcome=%s model=%s", call.id, outcome, model_tag)
    return analysis


async def classify_by_status(
    session: AsyncSession,
    call: Call,
) -> CallAnalysis:
    """Create a call_analysis row from the call's terminal status without an LLM call.

    Used for calls that never connected (no-answer, busy, failed, …) — outcome
    "not_reached" — and for completed calls that arrived without a transcript
    — outcome "no_output" (the call happened but produced nothing to analyse).
    """
    outcome = "no_output" if call.status == "completed" else "not_reached"

    now = datetime.now(timezone.utc)

    existing = await session.execute(
        select(CallAnalysis).where(CallAnalysis.call_id == call.id)
    )
    analysis = existing.scalar_one_or_none()

    if analysis is None:
        analysis = CallAnalysis(
            call_id=call.id,
            client_id=call.client_id,
            agent_id=call.agent_id,
            batch_id=call.batch_id,
        )
        session.add(analysis)

    analysis.outcome = outcome
    analysis.summary = f"Call ended with status: {call.status}"
    analysis.reason = (
        f"Auto-classified from terminal status '{call.status}' (no transcript)."
    )
    analysis.requests = []
    analysis.model_used = "status-classifier/v1"
    analysis.analyzed_at = now
    analysis.raw_llm_response = {"source": "status_classifier", "status": call.status}

    await session.flush()
    logger.info(
        "Call %s auto-classified: status=%s outcome=%s", call.id, call.status, outcome
    )
    return analysis


async def run_analysis_for_call(call_id: str, settings: Settings) -> None:
    """Analyse one call in its own session. Never raises.

    Completed calls with a transcript go to the LLM classifier; every other
    terminal status (including completed-without-transcript) goes to the
    status-based auto-classifier. Idempotent: returns early when an analysis row
    already exists.

    Lives in the service layer so both the webhook receiver and the batch
    reconcile path can schedule it without a service importing from a router.
    """
    import uuid as _uuid

    from app.core.call_status import CONNECTED_STATUSES
    from app.db.session import get_session_factory
    from app.services.tenants import get_config

    try:
        async with get_session_factory()() as session:
            call = await session.get(Call, _uuid.UUID(call_id))
            if call is None:
                return
            existing = await session.execute(
                select(CallAnalysis).where(CallAnalysis.call_id == call.id)
            )
            if existing.scalar_one_or_none() is not None:
                return  # already analysed

            if call.status in CONNECTED_STATUSES and call.transcript:
                client_config = await get_config(session, call.client_id)
                await analyze_call(session, call, settings, client_config)
            else:
                await classify_by_status(session, call)
            await session.commit()
    except Exception:
        logger.exception("Background analysis failed for call_id=%s", call_id)
