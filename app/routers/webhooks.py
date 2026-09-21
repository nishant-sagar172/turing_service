from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.call_status import normalize_batch_status
from app.config import Settings, get_settings
from app.db.session import get_session
from app.dependencies import get_voice_engine
from app.services.batch_sync import sync_batch_executions
from app.services.call_sync import complete_call, notify_batch_status, sync_execution
from app.services.outcome_notifier import build_batch_event
from app.services.store import get_batch_by_voice_id_global

logger = logging.getLogger("turing.webhooks")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Bolna sends this exact shape for BATCH campaigns — a batch-lifecycle summary
# (batch_id, status, valid_contacts, total_contacts, file_name, ...) with no
# execution id — instead of a per-call payload. Only single ad-hoc calls
# (POST /v1/calls) get a per-call execution webhook. Reaching one of these
# terminal statuses is our only signal that the batch's calls are ready to
# pull, so we react to it here rather than requiring a manual reconcile.
BATCH_TERMINAL_STATUSES = frozenset(
    {"completed", "stopped", "failed", "cancelled", "canceled"}
)


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

    status = normalize_batch_status(payload.get("status"))
    if status:
        batch.status = status
        background_tasks.add_task(
            notify_batch_status, batch.client_id, build_batch_event(batch)
        )

    synced = 0
    if status in BATCH_TERMINAL_STATUSES:
        voice_engine = get_voice_engine(request)
        items = await sync_batch_executions(
            session, voice_engine, batch, background_tasks, settings
        )
        synced = len(items)

    await session.commit()
    logger.info(
        "Batch webhook: batch=%s status=%s synced=%d",
        voice_batch_id,
        status,
        synced,
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
        return await _handle_batch_webhook(
            request, payload, background_tasks, session, settings
        )

    call, just_finished = await sync_execution(session, payload)
    if call is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_webhook_payload",
                "message": "Payload has no execution id, or cannot be attributed "
                "to a client.",
            },
        )
    await session.commit()

    # Bolna populates the transcript, recording and extracted_data on the
    # terminal `completed` event itself (call-disconnected is non-terminal and
    # carries none), so the terminal transition is the right and only trigger.
    if just_finished:
        background_tasks.add_task(complete_call, call.id, settings)

    logger.info(
        "Voice webhook: call=%s status=%s completing=%s",
        call.voice_call_id,
        call.status,
        just_finished,
    )
    return {
        "received": True,
        "execution_id": call.voice_call_id,
        "completing": just_finished,
    }
