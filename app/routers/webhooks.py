"""Inbound webhooks from Bolna (execution status pushes).

Not part of the client-facing /v1 surface. Access control is a source-IP
allowlist (``BOLNA_WEBHOOK_ALLOWED_IPS``; empty disables the check for dev /
simulated deliveries). The receiver ACKs fast and is idempotent — repeated
deliveries for the same execution simply re-upsert the same row.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Batch
from app.db.session import get_session
from app.services import kalaam_notifier
from app.services.store import extract_bolna_batch_id, upsert_call_from_execution

logger = logging.getLogger("turing.webhooks")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _check_source_ip(request: Request, settings: Settings) -> None:
    allowed = settings.bolna_webhook_ip_set
    if not allowed:
        return  # check disabled (dev / simulation)
    client_ip = request.client.host if request.client else None
    if client_ip not in allowed:
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Source IP not allowed."},
        )


@router.post("/bolna")
async def bolna_webhook(
    request: Request,
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Receive a Bolna execution payload, persist it, forward lean outcome."""
    _check_source_ip(request, settings)

    call = await upsert_call_from_execution(session, payload)
    if call is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_webhook_payload",
                "message": "Payload has no execution id.",
            },
        )

    # Resolve the Bolna batch id for the lean outcome (explicit query — async
    # sessions cannot lazy-load call.batch).
    bolna_batch_id = extract_bolna_batch_id(payload)
    if bolna_batch_id is None and call.batch_id is not None:
        result = await session.execute(
            select(Batch.bolna_batch_id).where(Batch.id == call.batch_id)
        )
        bolna_batch_id = result.scalar_one_or_none()

    outcome = kalaam_notifier.build_lean_outcome(call, bolna_batch_id)
    forwarded = await kalaam_notifier.forward_outcome(outcome)

    logger.info(
        "Bolna webhook: execution=%s status=%s forwarded=%s",
        call.bolna_execution_id, call.status, forwarded,
    )
    return {"received": True, "execution_id": call.bolna_execution_id,
            "forwarded": forwarded}
