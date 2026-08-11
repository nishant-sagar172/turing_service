from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Batch
from app.db.session import get_session, get_session_factory
from app.dependencies import get_voice_engine
from app.services import outcome_notifier
from app.services.analysis import analyze_call, classify_by_status
from app.services.analytics import CONNECTED, TERMINAL
from app.services.batch_sync import sync_batch_executions
from app.services.store import (
    extract_voice_batch_id,
    get_batch_by_voice_id_global,
    upsert_call_from_execution,
)
from app.services.tenants import get_config

logger = logging.getLogger("turing.webhooks")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Bolna sends this exact shape for BATCH campaigns — a batch-lifecycle summary
# (batch_id, status, valid_contacts, total_contacts, file_name, ...) with no
# execution id — instead of a per-call payload. Only single ad-hoc calls
# (POST /v1/calls) get a per-call execution webhook. Reaching one of these
# terminal statuses is our only signal that the batch's calls are ready to
# pull, so we react to it here rather than requiring a manual reconcile.
BATCH_TERMINAL_STATUSES = frozenset({"completed", "stopped", "failed", "cancelled", "canceled"})


def _check_source_ip(request: Request, settings: Settings) -> None:
    allowed = settings.voice_webhook_ip_set
    if not allowed:
        return
    client_ip = request.client.host if request.client else None
    if client_ip not in allowed:
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Source IP not allowed."},
        )


async def _run_analysis(call_id: str, settings: Settings) -> None:
    """Background task: opens its own session, fetches call + config, runs analysis.

    Completed calls with a transcript → LLM classifier.
    All other terminal statuses (and completed with no transcript) → status-based auto-classifier.
    """
    import uuid as _uuid

    try:
        async with get_session_factory()() as session:
            from app.db.models import Call, CallAnalysis
            from sqlalchemy import select as _select

            call = await session.get(Call, _uuid.UUID(call_id))
            if call is None:
                return
            existing = await session.execute(
                _select(CallAnalysis).where(CallAnalysis.call_id == call.id)
            )
            if existing.scalar_one_or_none() is not None:
                return  # already analysed

            if call.status in CONNECTED and call.transcript:
                client_config = await get_config(session, call.client_id)
                await analyze_call(session, call, settings, client_config)
            else:
                await classify_by_status(session, call)
            await session.commit()
    except Exception:
        logger.exception("Background analysis failed for call_id=%s", call_id)


async def _handle_batch_webhook(
    request: Request,
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
    session: AsyncSession,
    settings: Settings,
) -> dict[str, Any]:
    voice_batch_id = payload.get("batch_id")
    if not voice_batch_id:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_webhook_payload",
                "message": "Payload has no execution id or batch id.",
            },
        )
    voice_batch_id = str(voice_batch_id)

    batch = await get_batch_by_voice_id_global(session, voice_batch_id)
    if batch is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unknown_batch",
                "message": f"No batch with voice_batch_id '{voice_batch_id}'.",
            },
        )

    status = payload.get("status")
    if status:
        batch.status = str(status)

    synced = 0
    if status in BATCH_TERMINAL_STATUSES:
        voice_engine = get_voice_engine(request)
        items = await sync_batch_executions(session, voice_engine, batch, background_tasks, settings)
        synced = len(items)

    await session.commit()
    logger.info(
        "Batch webhook: batch=%s status=%s synced=%d",
        voice_batch_id, status, synced,
    )
    return {"received": True, "batch_id": voice_batch_id, "synced_calls": synced}


@router.post("/voice")
async def voice_webhook(
    request: Request,
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _check_source_ip(request, settings)

    if not (payload.get("id") or payload.get("execution_id")):
        return await _handle_batch_webhook(request, payload, background_tasks, session, settings)

    call = await upsert_call_from_execution(session, payload)
    if call is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_webhook_payload",
                "message": "Payload has no execution id, or cannot be attributed "
                "to a client.",
            },
        )

    voice_batch_id = extract_voice_batch_id(payload)
    if voice_batch_id is None and call.batch_id is not None:
        result = await session.execute(
            select(Batch.voice_batch_id).where(Batch.id == call.batch_id)
        )
        voice_batch_id = result.scalar_one_or_none()

    config = await get_config(session, call.client_id)
    outcome = outcome_notifier.build_lean_outcome(call, voice_batch_id)
    forwarded = await outcome_notifier.forward_outcome(
        outcome,
        webhook_url=config.webhook_url if config else None,
        webhook_secret=config.webhook_secret if config else None,
    )

    logger.info(
        "Voice webhook: call=%s status=%s forwarded=%s",
        call.voice_call_id, call.status, forwarded,
    )

    # Fire-and-forget analysis for all terminal calls.
    if call.status in TERMINAL:
        background_tasks.add_task(_run_analysis, str(call.id), settings)

    return {"received": True, "execution_id": call.voice_call_id, "forwarded": forwarded}
