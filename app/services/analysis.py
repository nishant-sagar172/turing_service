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

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.encryption import EncryptionError, decrypt
from app.db.models import Call, CallAnalysis, ClientConfig

logger = logging.getLogger("turing.analysis")

OUTCOME_BUCKETS = frozenset(
    {"booking", "escalation", "not_interested", "no_output", "follow_up", "other"}
)

_DEFAULT_MODELS = {"anthropic": "claude-haiku-4-5-20251001", "openai": "gpt-4o-mini"}

_SYSTEM_PROMPT = """\
You are a call outcome classifier for an outbound voice calling service.
Analyse the transcript and classify the call into exactly one outcome bucket.

Buckets:
- booking        : a confirmed appointment or booking was made
- escalation     : the call needs human follow-up or escalation
- not_interested : the person clearly declined or expressed no interest
- no_output      : call connected but no meaningful conversation occurred
- follow_up      : a follow-up call or action is required
- other          : does not fit any of the above categories\
"""

_TOOL_SCHEMA: dict[str, Any] = {
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
        },
        "required": ["outcome", "summary", "reason", "requests"],
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
    return settings.anthropic_api_key if provider == "anthropic" else settings.openai_api_key


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
        "summary (2-3 sentences), reason (string), requests (array of strings)."
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
            provider, call.id,
        )
        return None

    system = _SYSTEM_PROMPT
    if client_config and client_config.analysis_prompt_hint:
        system += f"\n\nClient context: {client_config.analysis_prompt_hint}"

    user_content = _build_user_content(call)

    try:
        if provider == "anthropic":
            result = await _call_anthropic(api_key, model, system, user_content)
        else:
            result = await _call_openai(api_key, model, system, user_content)
    except Exception:
        logger.exception("LLM analysis failed for call %s", call.id)
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

    analysis.outcome = outcome
    analysis.summary = result.get("summary") or ""
    analysis.reason = result.get("reason") or ""
    analysis.requests = result.get("requests") or []
    analysis.model_used = model_tag
    analysis.analyzed_at = now
    analysis.raw_llm_response = result

    await session.flush()
    logger.info(
        "Call %s analysed: outcome=%s model=%s", call.id, outcome, model_tag
    )
    return analysis
