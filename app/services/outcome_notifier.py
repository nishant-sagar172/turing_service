"""Forwards full call outcomes to a client's own callback endpoint.

Payload is signed with HMAC-SHA256 over the raw JSON body:
``X-Webhook-Signature: sha256=<hexdigest>``.

Forwarding is best-effort: failures are logged, never raised, so the inbound
voice-engine webhook is always ACKed (the reconcile poll covers missed
deliveries). The URL/secret are per-client (``client_config``), resolved by
the caller from the owning row's ``client_id`` before this is invoked.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from app.db.models import Batch, Call, CallAnalysis
from app.services.dispositions import resolve_legacy_disposition

logger = logging.getLogger("turing.notifier")


def build_outcome(
    call: Call, voice_batch_id: str | None, analysis: CallAnalysis | None = None
) -> dict[str, Any]:
    """The full call outcome forwarded to a client's webhook.

    Carries the complete record: call metadata, transcript, extracted data, and
    the entire analysis block (outcome + disposition + every classified field),
    so a client can act on the webhook alone without calling back. ``analysis``
    is None only when classification could not run (e.g. no LLM key configured).
    """
    from_number = call.from_number or (call.batch.from_number if call.batch else None)

    legacy = (
        resolve_legacy_disposition(analysis.workflow_code, analysis.call_outcome)
        if analysis
        else None
    )
    analysis_block = (
        {
            "call_outcome": analysis.call_outcome,
            "disposition_status": analysis.disposition_status,
            "sub_status": analysis.sub_status,
            "legacy_disposition_status": legacy.status if legacy else None,
            "legacy_sub_status": legacy.sub_status if legacy else None,
            "workflow_code": analysis.workflow_code,
            "summary": analysis.summary,
            "reason": analysis.reason,
            "requests": analysis.requests or [],
            "urgency": analysis.urgency,
            "confidence": analysis.confidence,
            "symptoms_reported": analysis.symptoms_reported or [],
            "model_used": analysis.model_used,
            "analyzed_at": (
                analysis.analyzed_at.isoformat() if analysis.analyzed_at else None
            ),
        }
        if analysis
        else None
    )
    return {
        "turing_call_id": str(call.id),
        "turing_batch_id": voice_batch_id,
        "voice_call_id": call.voice_call_id,
        "patient_uhid": call.patient_ref,
        "client_ref": call.client_ref,
        "contact_number": call.contact_number,
        "from_number": from_number,
        "agent_id": call.agent_id,
        "status": call.status,
        "recording_url": call.recording_url,
        "cost": call.cost,
        "duration": call.duration,
        "hangup_reason": call.hangup_reason,
        "retry_count": call.retry_count,
        "created_at": call.created_at.isoformat() if call.created_at else None,
        "transcript": call.transcript,
        "extracted_data": call.extracted_data,
        "analysis": analysis_block,
    }


def build_batch_event(batch: Batch) -> dict[str, Any]:
    """Batch lifecycle change forwarded to a client's webhook (no call id)."""
    return {
        "event": "batch.status",
        "turing_batch_id": batch.voice_batch_id,
        "status": batch.status,
        "valid_contacts": batch.valid_count,
        "total_contacts": batch.total_count,
        "scheduled_at": batch.scheduled_at,
    }


def batch_event_url(webhook_url: str) -> str:
    """The client's outcome URL ends in /call-completed; batch events go to /events."""
    base, sep, tail = webhook_url.rstrip("/").rpartition("/")
    return f"{base}/events" if sep and tail == "call-completed" else webhook_url


def sign_body(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def forward_outcome(
    outcome: dict[str, Any],
    *,
    webhook_url: str | None,
    webhook_secret: str | None,
) -> bool:
    """POST the lean outcome to the client's configured webhook_url."""
    if not webhook_url:
        logger.debug("No webhook_url configured for this client; forwarding disabled.")
        return False

    body = json.dumps(outcome, default=str).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if webhook_secret:
        headers["X-Webhook-Signature"] = sign_body(body, webhook_secret)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, content=body, headers=headers)
        if response.is_error:
            logger.warning(
                "Client callback returned %s for call %s",
                response.status_code,
                outcome.get("turing_call_id"),
            )
            return False
        return True
    except httpx.HTTPError as exc:
        logger.warning(
            "Client callback failed for call %s: %s",
            outcome.get("turing_call_id"),
            exc,
        )
        return False
