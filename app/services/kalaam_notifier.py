"""Forwards lean call outcomes to the consumer's callback endpoint (Kalaam).

Payload is signed with HMAC-SHA256 over the raw JSON body:
``X-Webhook-Signature: sha256=<hexdigest>`` — the same scheme Kalaam already
uses for its WhatsApp integration webhooks.

Forwarding is best-effort: failures are logged, never raised, so the Bolna
webhook is always ACKed (the reconcile poll covers missed deliveries).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.db.models import Call

logger = logging.getLogger("turing.notifier")


def build_lean_outcome(call: Call, bolna_batch_id: str | None) -> dict[str, Any]:
    """The lean outcome contract consumers store (full record stays in turing)."""
    return {
        "turing_execution_id": call.bolna_execution_id,
        "turing_call_id": str(call.id),
        "turing_batch_id": bolna_batch_id,
        "patient_uhid": call.patient_ref,
        "contact_number": call.contact_number,
        "agent_id": call.agent_id,
        "status": call.status,
        "disposition": None,  # reserved for the later analytics phase
        "recording_url": call.recording_url,
        "cost": call.cost,
        "duration": call.duration,
        "hangup_reason": call.hangup_reason,
    }


def sign_body(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def forward_outcome(outcome: dict[str, Any]) -> bool:
    """POST the lean outcome to KALAAM_WEBHOOK_URL. Returns delivery success."""
    settings = get_settings()
    if not settings.kalaam_webhook_url:
        logger.debug("KALAAM_WEBHOOK_URL unset; outcome forwarding disabled.")
        return False

    body = json.dumps(outcome, default=str).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if settings.kalaam_webhook_secret:
        headers["X-Webhook-Signature"] = sign_body(
            body, settings.kalaam_webhook_secret
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.kalaam_webhook_url, content=body, headers=headers
            )
        if response.is_error:
            logger.warning(
                "Kalaam callback returned %s for execution %s",
                response.status_code, outcome.get("turing_execution_id"),
            )
            return False
        return True
    except httpx.HTTPError as exc:
        logger.warning(
            "Kalaam callback failed for execution %s: %s",
            outcome.get("turing_execution_id"), exc,
        )
        return False
