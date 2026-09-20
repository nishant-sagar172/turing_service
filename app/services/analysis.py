"""LLM-based call outcome classification.

Resolution order for provider / model / API key:
  1. client_config.analysis_llm_* (per-client override)
  2. Settings.llm_* (system env vars)
  3. Skip — log warning, return None without crashing the caller.

Both Anthropic and OpenAI paths enforce structured output via tool/schema
constraints — the model cannot return values outside the allowed enum set.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

_MAX_ANALYSIS_ATTEMPTS = 3
_ANALYSIS_BACKOFF_S = 1.0


def _is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
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
from app.db.models import Batch, Call, CallAnalysis, ClientConfig
from app.services.dispositions import resolve_disposition
from app.services.workflows import (
    DEFAULT_WORKFLOW_CODE,
    NOT_CONNECTED_OUTCOME,
    WORKFLOWS,
    outcomes_for_workflow,
    resolve as resolve_workflow,
)

logger = logging.getLogger("turing.analysis")

# Marks an analysis derived from the call status alone, with no transcript.
STATUS_CLASSIFIER_MODEL = "status-classifier/v1"

# ── Outcome taxonomy ─────────────────────────────────────────────────────────

URGENCY_LEVELS = frozenset({"low", "medium", "high"})

_DEFAULT_MODELS = {"anthropic": "claude-haiku-4-5-20251001", "openai": "gpt-5.6-luna"}


# ── Prompt builder ────────────────────────────────────────────────────────────

_PREAMBLE = """\
You are a call outcome classifier for an outbound patient healthcare voice \
service (follow-ups, appointment reminders, check-ins, admission coordination).

Transcripts are Hindi, English, or Hinglish with transcription noise and \
disfluencies — classify by INTENT, not exact wording. Read the FULL transcript; \
the outcome often depends on the last few exchanges.

Classify into exactly ONE call_outcome. Return the single best match."""

_OUTCOME_DEFS_COMMON = """\

OUTCOMES (pick exactly one):

- escalation: Patient or relative reports ANY active/worsening symptom, adverse \
drug reaction, self-harm/suicidal mention, or explicitly requests urgent callback. \
HIGHEST PRIORITY — if escalation criteria are met alongside any other outcome, \
always pick escalation.
  Signals: "दर्द हो रहा है", "बुखार आ रहा है", "sugar बहुत high हो गया", \
"सूजन है", "तकलीफ़ बढ़ गई", "urgent appointment चाहिए"
  Still classify urgency, symptoms_reported, and requests as normal.

- completed_visited: Patient or family confirms the visit/admission/procedure \
has ALREADY been completed at THIS hospital. Already happened, past tense.
  Signals: "आज ही consult करके आए", "ho gaya", "admit ho chuke hain", \
"kal hi surgery hui", "already came", "procedure done", "दिखा के आए हैं"
  NOT: "aayenge" (future — that's scheduled_booking)

- scheduled_booking: A specific date/appointment is FIXED and CONFIRMED for the \
future. Patient or family explicitly agrees to a proposed slot or names one.
  Signals: "हां कर दीजिए", "10 September ko aa jayenge", "book kar do", \
"हां perfect", "दस सितंबर को"
  NOT: "dekhte hain", "sochenge", "try karenge", "maybe next week" (follow_up)
  NOT: date proposed by agent but patient hasn't confirmed (follow_up)

- done_elsewhere: Patient was treated/admitted at a DIFFERENT hospital. \
Decision is final — they are not coming here.
  Signals: "doosre hospital mein karwa liya", "we went to [other hospital]", \
"already admitted elsewhere", "wahan se treatment ho gaya"

- wants_cost_estimate: Patient asking for approximate cost/package price \
BEFORE deciding. No commitment yet.
  Signals: "kitna kharcha aayega", "package cost kya hai", "estimate bhej do"

- wants_discount: Patient HAS the cost estimate but finds it too expensive. \
Asking for discount/negotiation.
  Signals: "bahut zyada hai", "kuch discount milega", "afford nahi kar sakte\""""

_OUTCOME_DEFS_TAIL = """

- waiting_doctor_confirmation: Doctor's final go-ahead still pending.
  Signals: "doctor se puchna hai", "doctor ne abhi nahi bola"

- waiting_referral_letter: A referral document (e.g. from the primary doctor \
or insurer) is still required before proceeding.
  Signals: "referral letter nahi aaya", "insurer se letter chahiye", \
"referral chahiye hoga"

- wants_second_opinion: Patient wants another doctor's opinion before deciding.
  Signals: "doosre doctor se dikhayenge", "second opinion lena hai"

- follow_up: Patient ACTIVELY asks to be contacted again or is undecided but \
not refusing. They give a reason for delay or say "call later".
  Signals: "baad mein call karo", "sochenge", "family se baat karke batata \
hoon", "main call karunga", "verify karke batata hoon", "dekhte hain"
  NOT: call just ending abruptly with no patient response (that's call_dropped)
  NOT: explicit "nahi karwana" / "don't call again" (that's declined)

- call_dropped: Call was connected and real conversation happened (at minimum \
patient identity was confirmed AND some health/appointment discussion began), \
but the call ended abruptly WITHOUT a conclusion. No booking, no refusal, no \
explicit follow-up request — the call just stopped.
  Signals: transcript ends mid-sentence, agent says "हेलो, आप लाइन पर हैं?" \
or "Have a good day" after silence, no closure from patient side, agent's \
last message is unanswered.
  NOT: greeting-only calls with no health discussion (that's no_output)

- declined: Patient EXPLICITLY and UNAMBIGUOUSLY refuses to proceed with this \
hospital/treatment. Clear refusal language, not just declining a specific date.
  Signals: "nahi karwana hai", "don't call again", "not interested", \
"cancel karo", "remove my number", "kisi doctor ke paas nahi jana"
  NOT: "नहीं" to a specific proposed date (that's follow_up if they want \
another date, or call_dropped if call ends)
  NOT: curt tone alone — need explicit refusal words

- no_output: Call connected but no meaningful patient interaction. Only \
greetings and/or identity check, OR wrong number, OR voicemail/IVR, OR \
immediate hangup, OR dead air, OR unintelligible transcript.
  Signals: transcript is just "hello" + introduction + silence/hangup, \
"wrong number hai", third party can't relay, "Have a good day" after \
no response to first question.
  NOT: patient confirmed identity AND health was discussed (call_dropped)"""

# Highest priority first. Rendered per workflow so the chain never names an
# outcome the schema forbids for that campaign.
_PRIORITY_ORDER = (
    "escalation",
    "scheduled_booking",
    "completed_visited",
    "done_elsewhere",
    "wants_cost_estimate",
    "wants_discount",
    "insurance_concern",
    "loan_required",
    "wants_second_opinion",
    "on_medications",
    "waiting_doctor_confirmation",
    "waiting_reports",
    "medical_clearance_pending",
    "waiting_referral_letter",
    "call_dropped",
    "follow_up",
    "declined",
    "no_output",
)

_RULES = """

STRICT RULES:
1. A patient saying "नहीं" to a SPECIFIC DATE is NOT declined — it is \
follow_up (if they indicate willingness to reschedule) or call_dropped \
(if the call ends without resolution).
2. A patient saying they are fine / "ठीक हूं" and the call ending without \
reaching the appointment question = call_dropped, NOT no_output \
(health was discussed).
3. Every call MUST map to one of the listed outcomes. There is no "other" bucket.
4. If confidence < 0.7 and you are torn between two outcomes, pick the one \
that is SAFER for the patient (escalation > follow_up > declined).
5. Third party answering: classify based on what the third party communicates. \
"Patient is fine, we'll come" = follow_up. "Patient went elsewhere" = \
done_elsewhere. Third party can't relay = no_output.

ASSESSMENT (fill for every call):
- urgency: "low" (routine), "medium" (needs attention within days), \
"high" (needs same-day/next-day human review — acute symptoms, adverse \
reaction, vulnerable patient)
- confidence: 0.0-1.0. Lower for: unclear audio, heavy code-switching, \
ambiguous intent, transcript cut off at critical moment
- symptoms_reported: ANY symptom mentioned, in ANY outcome — not just \
escalation. Include denied symptoms as "[symptom] (denied)".
- requests: concrete asks the patient made
- summary: 2-3 sentences. What happened on the call, who spoke, what was \
the outcome.
- reason: Why you chose this call_outcome. One sentence."""

_FEW_SHOT = """

EXAMPLES (from real production calls):

EXAMPLE 1 — call_dropped:
Agent asks about health. Patient's wife says "ठीक है". Agent proposes \
10 September appointment. No response. Agent says "हेलो, आप लाइन पर हैं?" \
Call ends.
→ call_outcome: "call_dropped" (appointment proposed but call ended with \
no response — no confirmation, no refusal, no "call later")

EXAMPLE 2 — completed_visited:
Agent asks about health. Son says "ma'am आज ही consult करके आए हूं" and \
"after fifteen days होगा". Declines booking, says "मैं doctor को call करके \
pick up कर लेता हूं".
→ call_outcome: "completed_visited" (patient already visited today, \
follow-up timeline is set by doctor)

EXAMPLE 3 — scheduled_booking:
Agent asks if patient wants 10 September appointment. Patient says \
"दस सितंबर कर दीजिए ठीक है". Agent confirms "appointment book कर दी गई है".
→ call_outcome: "scheduled_booking" (explicit confirmation of specific date)

EXAMPLE 4 — escalation:
Agent asks about joint/knee/back pain. Patient says "हां अभी है जी" and \
"कल परसों है sir चालू होकर". Agent arranges urgent appointment.
→ call_outcome: "escalation" (ongoing/worsening pain reported)

EXAMPLE 5 — declined:
Agent proposes follow-up. Patient says "नहीं ma'am", explains "मेरी तबीयत \
बिल्कुल fine है" and "ठीक नहीं होंगे तभी तो आऐंगे ना". Firm refusal, \
will come only if sick.
→ call_outcome: "declined" (explicit, repeated refusal of follow-up care)

EXAMPLE 6 — follow_up:
Agent proposes 10 September. Son says "यह one thing मैं उनसे verify करूंगा" \
and "मैं call करूंगा".
→ call_outcome: "follow_up" (actively deferred — will check and call back)

EXAMPLE 7 — no_output:
Agent introduces herself, asks "क्या मैं X जी से बात कर रही हूँ?" Patient \
says "नहीं wrong number है". Agent ends call.
→ call_outcome: "no_output" (wrong number, no patient interaction)

EXAMPLE 8 — escalation (adverse drug reaction):
Relative says "doctor को बताया गया है कि mommy को sugar है उसके बावजूद \
उन्होंने medicine ऐसी दी जिससे उनका sugar high हो गया". Declines appointment.
→ call_outcome: "escalation" (adverse drug reaction — escalation overrides \
the declined appointment)"""


def _build_priority_order(workflow_code: str | None) -> str:
    valid = outcomes_for_workflow(workflow_code)
    chain = " > ".join(o for o in _PRIORITY_ORDER if o in valid)
    return (
        f"\n\nPRIORITY ORDER (if multiple outcomes apply, pick the highest):\n{chain}"
    )


def _build_system_prompt(
    workflow_code: str | None, prompt_hint: str | None = None
) -> str:
    # A workflow's own definitions splice in between the shared blocks, so a
    # new workflow needs no change here — only a registry entry.
    parts = [_PREAMBLE, _OUTCOME_DEFS_COMMON]
    section = resolve_workflow(workflow_code).prompt_section
    if section:
        parts.append(section)
    parts.append(_OUTCOME_DEFS_TAIL)
    parts.append(_build_priority_order(workflow_code))
    parts.append(_RULES)
    parts.append(_FEW_SHOT)
    prompt = "".join(parts)
    if prompt_hint:
        prompt += f"\n\nClient context: {prompt_hint}"
    return prompt


# ── Tool schema builder ──────────────────────────────────────────────────────


def _build_tool_schema(workflow_code: str | None) -> dict[str, Any]:
    valid = outcomes_for_workflow(workflow_code)
    return {
        "name": "classify_call",
        "description": "Classify a call outcome and generate structured analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "call_outcome": {
                    "type": "string",
                    "enum": sorted(valid),
                },
                "summary": {
                    "type": "string",
                    "description": "2-3 sentence plain-language summary of the call.",
                },
                "reason": {
                    "type": "string",
                    "description": "Why this call_outcome was assigned.",
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
                "call_outcome",
                "summary",
                "reason",
                "requests",
                "urgency",
                "confidence",
                "symptoms_reported",
            ],
        },
    }


# ── Provider / model / key resolution ─────────────────────────────────────────


def _resolve_provider_model(
    settings: Settings, config: ClientConfig | None
) -> tuple[str, str]:
    provider = (
        (config.analysis_llm_provider if config else None)
        or settings.llm_provider
        or "openai"
    )
    model = (
        (config.analysis_llm_model if config else None)
        or settings.llm_model
        or _DEFAULT_MODELS.get(provider, "gpt-5.6-luna")
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


# ── LLM client caching ───────────────────────────────────────────────────────

# Keyed by api_key. An async provider client owns an httpx connection pool that
# must be aclose()d; lru_cache eviction drops the client without closing it,
# leaking the pool. These clients are long-lived and few (one per distinct key),
# so a plain unbounded cache — never evicting, never leaking — is the right fit.
_anthropic_clients: dict[str, Any] = {}
_openai_clients: dict[str, Any] = {}


def _get_anthropic_client(api_key: str) -> Any:
    client = _anthropic_clients.get(api_key)
    if client is None:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key)
        _anthropic_clients[api_key] = client
    return client


def _get_openai_client(api_key: str) -> Any:
    client = _openai_clients.get(api_key)
    if client is None:
        import openai

        client = openai.AsyncOpenAI(api_key=api_key)
        _openai_clients[api_key] = client
    return client


# ── Provider call helpers ─────────────────────────────────────────────────────


def _build_user_content(call: Call) -> str:
    parts = [f"TRANSCRIPT:\n{call.transcript}"]
    if call.extracted_data:
        parts.append(f"EXTRACTED DATA:\n{json.dumps(call.extracted_data, indent=2)}")
    return "\n\n".join(parts)


async def _call_anthropic(
    api_key: str,
    model: str,
    system: str,
    user_content: str,
    tool_schema: dict[str, Any],
) -> dict[str, Any]:
    client = _get_anthropic_client(api_key)
    response = await client.messages.create(
        model=model,
        # Headroom for the full structured output (summary + reason + two
        # arrays): 1024 truncated verbose calls, which then hard-fail as
        # unretryable and never get an analysis row at all.
        max_tokens=2048,
        system=system,
        tools=[tool_schema],
        tool_choice={"type": "tool", "name": "classify_call"},
        messages=[{"role": "user", "content": user_content}],
    )
    # A truncated response leaves the tool_use input partially populated, which
    # would surface as a missing call_outcome and get silently downgraded — so
    # treat truncation as a hard failure rather than classifying on half a JSON.
    if getattr(response, "stop_reason", None) == "max_tokens":
        raise ValueError("Anthropic response truncated at max_tokens")
    for block in response.content:
        if block.type == "tool_use" and block.name == "classify_call":
            return dict(block.input)
    raise ValueError("No classify_call tool_use block in Anthropic response")


async def _call_openai(
    api_key: str,
    model: str,
    system: str,
    user_content: str,
    tool_schema: dict[str, Any],
) -> dict[str, Any]:
    client = _get_openai_client(api_key)
    json_schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "classify_call",
            "strict": True,
            "schema": {
                **tool_schema["input_schema"],
                "additionalProperties": False,
            },
        },
    }
    response = await client.chat.completions.create(
        model=model,
        response_format=json_schema,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    )
    message = response.choices[0].message
    # A refusal (or any empty completion) carries no content. Parsing it as "{}"
    # would let the caller's default silently record a `follow_up` that is never
    # retried, so fail loudly and leave the call unanalysed instead.
    refusal = getattr(message, "refusal", None)
    if refusal:
        raise ValueError(f"OpenAI refused to classify the call: {refusal}")
    if not message.content:
        raise ValueError("Empty content in OpenAI response")
    parsed = json.loads(message.content)
    if not isinstance(parsed, dict):
        raise ValueError("OpenAI response was not a JSON object")
    return parsed


# ── Core analysis ─────────────────────────────────────────────────────────────


async def _resolve_workflow_code(
    session: AsyncSession,
    call: Call,
    client_config: ClientConfig | None,
) -> str:
    """Calling workflow: the call's own (single calls), its batch, then the
    client default.

    Every level is optional — a batch with no workflow, for a client with no
    default, classifies against the common outcome set under DEFAULT_WORKFLOW_CODE.
    """
    if call.workflow_code in WORKFLOWS:
        return str(call.workflow_code)
    if call.batch_id is not None:
        batch_workflow_code = (
            await session.execute(
                select(Batch.workflow_code).where(Batch.id == call.batch_id)
            )
        ).scalar_one_or_none()
        if batch_workflow_code in WORKFLOWS:
            return str(batch_workflow_code)
    if client_config and client_config.default_workflow_code in WORKFLOWS:
        return str(client_config.default_workflow_code)
    return DEFAULT_WORKFLOW_CODE


async def analyze_call(
    session: AsyncSession,
    call: Call,
    settings: Settings,
    client_config: ClientConfig | None = None,
) -> CallAnalysis | None:
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

    workflow_code = await _resolve_workflow_code(session, call, client_config)
    prompt_hint = client_config.analysis_prompt_hint if client_config else None
    system = _build_system_prompt(workflow_code, prompt_hint)
    tool_schema = _build_tool_schema(workflow_code)
    user_content = _build_user_content(call)

    valid_outcomes = outcomes_for_workflow(workflow_code)

    result: dict[str, Any] | None = None
    for attempt in range(_MAX_ANALYSIS_ATTEMPTS):
        try:
            if provider == "anthropic":
                result = await _call_anthropic(
                    api_key, model, system, user_content, tool_schema
                )
            else:
                result = await _call_openai(
                    api_key, model, system, user_content, tool_schema
                )
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

    if result is None:
        return None

    # OpenAI's strict schema makes an out-of-set value impossible; Anthropic's
    # tool schema is advisory, so a hallucinated or cross-workflow outcome can
    # still arrive. On this healthcare classifier an unrecognised value must
    # fail SAFE, not silently become follow_up: downgrading a mislabelled
    # escalation to a routine follow-up buries a patient-safety event. Record
    # escalation instead — it is valid in every workflow and maps to the
    # "Escalation" disposition, so a human always reviews it.
    call_outcome = result.get("call_outcome")
    if call_outcome not in valid_outcomes:
        logger.error(
            "Call %s: model returned unusable call_outcome %r for workflow_code %r "
            "(provider=%s) — recording escalation for human review. Valid outcomes: %s",
            call.id,
            call_outcome,
            workflow_code,
            provider,
            sorted(valid_outcomes),
        )
        call_outcome = "escalation"

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

    disposition = resolve_disposition(workflow_code, call_outcome)

    analysis.call_outcome = call_outcome
    analysis.disposition_status = disposition.status
    analysis.sub_status = disposition.sub_status
    analysis.workflow_code = workflow_code
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
    logger.info(
        "Call %s analysed: call_outcome=%s disposition=%s/%s model=%s",
        call.id,
        call_outcome,
        disposition.status,
        disposition.sub_status,
        model_tag,
    )
    return analysis


async def classify_by_status(
    session: AsyncSession,
    call: Call,
    client_config: ClientConfig | None = None,
) -> CallAnalysis:
    call_outcome = "no_output" if call.status == "completed" else NOT_CONNECTED_OUTCOME
    workflow_code = await _resolve_workflow_code(session, call, client_config)

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

    disposition = resolve_disposition(workflow_code, call_outcome)

    analysis.call_outcome = call_outcome
    analysis.disposition_status = disposition.status
    analysis.sub_status = disposition.sub_status
    analysis.workflow_code = workflow_code
    analysis.summary = f"Call ended with status: {call.status}"
    analysis.reason = (
        f"Auto-classified from terminal status '{call.status}' (no transcript)."
    )
    analysis.requests = []
    analysis.model_used = STATUS_CLASSIFIER_MODEL
    analysis.analyzed_at = now
    analysis.raw_llm_response = {"source": "status_classifier", "status": call.status}

    await session.flush()
    logger.info(
        "Call %s auto-classified: status=%s call_outcome=%s",
        call.id,
        call.status,
        call_outcome,
    )
    return analysis


async def run_analysis_for_call(call_id: str, settings: Settings) -> None:
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
            analysis = existing.scalar_one_or_none()
            # The engine fires several webhooks per call and fills fields late,
            # so the first terminal one can arrive before the transcript. Only
            # a status-only guess may be replaced once the transcript lands.
            upgrading = (
                analysis is not None
                and analysis.model_used == STATUS_CLASSIFIER_MODEL
                and call.status in CONNECTED_STATUSES
                and bool(call.transcript)
            )
            if analysis is not None and not upgrading:
                return

            client_config = await get_config(session, call.client_id)
            readable = bool(call.status in CONNECTED_STATUSES and call.transcript)
            if readable:
                await analyze_call(session, call, settings, client_config)
                if upgrading:
                    # The client was notified of the status-only guess; let the
                    # corrected outcome be claimed and sent again.
                    call.notified_at = None
            else:
                await classify_by_status(session, call, client_config)
            await session.commit()
    except Exception:
        logger.exception("Background analysis failed for call_id=%s", call_id)
