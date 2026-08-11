"""Pulls a batch's executions from the voice engine and syncs them into
``calls``. Shared by the manual reconcile GET (app/routers/batches.py) and
the automatic sync triggered by Bolna's batch-completion webhook
(app/routers/webhooks.py) — both need the exact same upsert + analysis-
trigger behavior, just from different entry points.
"""

from __future__ import annotations

from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.voice_engine import VoiceEngineClient
from app.db.models import Batch
from app.services.analytics import TERMINAL
from app.services.store import upsert_call_from_execution


async def sync_batch_executions(
    session: AsyncSession,
    voice_engine: VoiceEngineClient,
    batch: Batch,
    background_tasks: BackgroundTasks,
    settings: Settings,
) -> list[dict[str, Any]]:
    """Fetch every execution for ``batch`` from the voice engine, upsert each
    into ``calls``, and schedule analysis for any that are terminal."""
    from app.routers.webhooks import _run_analysis  # lazy: avoids import cycle

    result = await voice_engine.get_batch_executions(batch.voice_batch_id)
    items = [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []

    for item in items:
        item.setdefault("batch_id", batch.voice_batch_id)
        call = await upsert_call_from_execution(session, item, client_id=batch.client_id)
        if call and call.status in TERMINAL:
            background_tasks.add_task(_run_analysis, str(call.id), settings)

    return items
