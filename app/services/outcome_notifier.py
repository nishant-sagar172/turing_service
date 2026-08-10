"""Forwards lean call outcomes to a client's own callback endpoint.

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

from app.db.models import Call

logger = logging.getLogger("turing.notifier")


def build_lean_outcome(call: Call, voice_batch_id: str | None) -> dict[str, Any]:
    """The lean outcome contract a client stores (full record stays in turing)."""
    return {
        "turing_call_id": str(call.id),
        "turing_batch_id": voice_batch_id,
        "voice_call_id": call.voice_call_id,
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
                response.status_code, outcome.get("turing_call_id"),
            )
            return False
        return True
    except httpx.HTTPError as exc:
        logger.warning(
            "Client callback failed for call %s: %s",
            outcome.get("turing_call_id"), exc,
        )
        return False
