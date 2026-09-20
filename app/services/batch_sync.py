"""Pulls a batch's executions from the voice engine and syncs them into
``calls``. Shared by the manual reconcile GET (app/routers/batches.py) and
the automatic sync triggered by Bolna's batch-completion webhook
(app/routers/webhooks.py) — both need the exact same upsert + completion
behavior, just from different entry points.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.voice_engine import VoiceEngineClient
from app.db.models import Batch
from app.services.analytics import TERMINAL
from app.services.call_sync import complete_call, sync_execution

logger = logging.getLogger("turing.batch_sync")


async def sync_batch_executions(
    session: AsyncSession,
    voice_engine: VoiceEngineClient,
    batch: Batch,
    background_tasks: BackgroundTasks,
    settings: Settings,
) -> list[dict[str, Any]]:
    """Fetch every execution for ``batch`` from the voice engine, upsert each
    into ``calls``, and complete the ones that just finished."""
    if batch.voice_batch_id is None:
        return []
    result = await voice_engine.get_batch_executions(batch.voice_batch_id)
    items: list[dict[str, Any]] = cast(
        list[dict[str, Any]],
        [item for item in result if isinstance(item, dict)]
        if isinstance(result, list)
        else [],
    )

    for item in items:
        # Per-item isolation via a savepoint: a malformed execution rolls back
        # only its own changes, not every prior item's upsert in this pass. The
        # previous session-wide rollback discarded the whole pass on one bad item.
        try:
            async with session.begin_nested():
                item.setdefault("batch_id", batch.voice_batch_id)
                call, _ = await sync_execution(session, item, client_id=batch.client_id)
        except Exception:
            logger.exception(
                "skipping execution %s while syncing batch %s",
                item.get("id"),
                batch.voice_batch_id,
            )
            continue
        # Every terminal call goes to completion; the notified_at claim inside
        # complete_call makes re-processing a no-op, so a call finished in an
        # earlier pass is analysed once and forwarded once.
        if call is not None and call.status in TERMINAL:
            background_tasks.add_task(complete_call, call.id, settings)

    # Background completion reads these rows from its own session.
    await session.commit()
    return items
