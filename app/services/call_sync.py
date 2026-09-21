"""Brings single calls to completion: status sync, analysis, client notification.

Bolna's ``POST /call`` accepts no ``webhook_url``, so a single call only reaches
``/webhooks/voice`` when its agent has one configured. The polling pass here is
the fallback. Every path that sees a call turn terminal hands it to
``complete_call`` exactly once.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.core.call_status import TERMINAL_STATUSES
from app.core.voice_engine import VoiceEngineClient, VoiceEngineError
from app.db.models import Call
from app.db.session import get_session_factory
from app.services import outcome_notifier
from app.services.analysis import run_analysis_for_call
from app.services.store import get_call_by_voice_id_global, upsert_call_from_execution
from app.services.tenants import get_config

logger = logging.getLogger("turing.call_sync")

# Scheduled calls can stay queued for days; anything older is treated as abandoned.
_LOOKBACK = timedelta(days=7)
_MAX_CALLS_PER_PASS = 200

# Bounds concurrent completions (each holds a DB session briefly plus an LLM call
# and an HTTP POST). Sized lazily from Settings on first use; a module-level
# singleton so every entry point shares the one budget.
_completion_semaphore: asyncio.Semaphore | None = None


def _get_completion_semaphore(settings: Settings) -> asyncio.Semaphore:
    global _completion_semaphore
    if _completion_semaphore is None:
        _completion_semaphore = asyncio.Semaphore(settings.completion_concurrency)
    return _completion_semaphore


async def sync_execution(
    session: AsyncSession,
    execution: dict[str, Any],
    client_id: uuid.UUID | None = None,
) -> tuple[Call | None, bool]:
    """Upsert an execution; the flag is True only when this update made the call terminal."""
    execution_id = execution.get("id") or execution.get("execution_id")
    existing_call = (
        await get_call_by_voice_id_global(session, str(execution_id))
        if execution_id
        else None
    )
    previous_status = existing_call.status if existing_call else None
    call = await upsert_call_from_execution(session, execution, client_id=client_id)
    just_finished = (
        call is not None
        and call.status in TERMINAL_STATUSES
        and previous_status not in TERMINAL_STATUSES
    )
    return call, just_finished


async def complete_call(call_id: uuid.UUID, settings: Settings) -> None:
    """Analyse a finished call, then send its outcome to the client's webhook.

    Safe to call from more than one path for the same call (webhook, poll,
    reconcile, batch sync): the outcome is claimed with a conditional UPDATE, so
    exactly one caller forwards it. A delivery failure releases the claim so the
    recovery pass retries; a crash before delivery leaves the claim unset, so the
    recovery pass picks it up too.
    """
    async with _get_completion_semaphore(settings):
        # Idempotent — no-op when an analysis row already exists.
        await run_analysis_for_call(str(call_id), settings)

        async with get_session_factory()() as session:
            claimed = (
                await session.execute(
                    update(Call)
                    .where(Call.id == call_id, Call.notified_at.is_(None))
                    .values(notified_at=datetime.now(timezone.utc))
                    .returning(Call.id)
                )
            ).scalar_one_or_none()
            if claimed is None:
                # Another path already owns this call's notification, or the row
                # is gone. Nothing to do.
                await session.commit()
                return

            call = (
                await session.execute(
                    select(Call)
                    .options(selectinload(Call.analysis), selectinload(Call.batch))
                    .where(Call.id == call_id)
                )
            ).scalar_one_or_none()
            if call is None:
                await session.commit()
                return

            config = await get_config(session, call.client_id)
            webhook_url = config.webhook_url if config else None
            webhook_secret = config.webhook_secret if config else None
            # Build the payload while the row is loaded, then commit to release
            # the connection BEFORE the outbound HTTP call — never hold a pooled
            # connection across a client webhook that can block for its timeout.
            outcome = outcome_notifier.build_outcome(
                call,
                call.batch.voice_batch_id if call.batch else None,
                call.analysis,
            )
            await session.commit()

        if not webhook_url:
            logger.info("Call %s completed: no webhook configured", call_id)
            return

        forwarded = await outcome_notifier.forward_outcome(
            outcome,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
        )
        if not forwarded:
            # Release the claim so a later recovery pass retries delivery.
            async with get_session_factory()() as session:
                await session.execute(
                    update(Call).where(Call.id == call_id).values(notified_at=None)
                )
                await session.commit()
        logger.info("Call %s completed: forwarded=%s", call_id, forwarded)


async def notify_batch_status(client_id: uuid.UUID, event: dict[str, Any]) -> bool:
    """Forward a batch lifecycle change to the client's webhook. Best-effort.

    Takes the already-built event so it never depends on the caller's
    transaction having committed.
    """
    async with get_session_factory()() as session:
        config = await get_config(session, client_id)
        webhook_url = config.webhook_url if config else None
        webhook_secret = config.webhook_secret if config else None
    if not webhook_url:
        return False
    forwarded = await outcome_notifier.forward_outcome(
        event,
        webhook_url=outcome_notifier.batch_event_url(webhook_url),
        webhook_secret=webhook_secret,
    )
    logger.info(
        "Batch %s status=%s forwarded=%s",
        event.get("turing_batch_id"), event.get("status"), forwarded,
    )
    return forwarded


async def sync_open_single_calls(
    session: AsyncSession, voice_engine: VoiceEngineClient, settings: Settings
) -> int:
    """Refresh open single calls from the voice engine; complete the ones that finished."""
    cutoff = datetime.now(timezone.utc) - _LOOKBACK
    open_calls = (
        (
            await session.execute(
                select(Call)
                .where(
                    Call.batch_id.is_(None),
                    Call.voice_call_id.isnot(None),
                    Call.status.notin_(TERMINAL_STATUSES),
                    Call.created_at >= cutoff,
                )
                .order_by(Call.created_at)
                .limit(_MAX_CALLS_PER_PASS)
            )
        )
        .scalars()
        .all()
    )

    finished_call_ids: list[uuid.UUID] = []
    for open_call in open_calls:
        try:
            execution = await voice_engine.get_execution(str(open_call.voice_call_id))
        except VoiceEngineError:
            logger.warning("could not fetch execution %s", open_call.voice_call_id)
            continue
        if not isinstance(execution, dict):
            continue
        # Per-item isolation: a malformed execution must roll back only its own
        # savepoint, not discard every other call's update in this pass.
        try:
            async with session.begin_nested():
                call, just_finished = await sync_execution(
                    session, execution, client_id=open_call.client_id
                )
        except Exception:
            logger.exception(
                "skipping execution %s while syncing open calls",
                open_call.voice_call_id,
            )
            continue
        if call is not None and just_finished:
            finished_call_ids.append(call.id)
    await session.commit()

    for finished_call_id in finished_call_ids:
        await complete_call(finished_call_id, settings)
    return len(finished_call_ids)


async def recover_unnotified_calls(session: AsyncSession, settings: Settings) -> int:
    """Re-drive completion for terminal calls that never notified the client.

    The durable backstop for both single and batch calls: a process restart
    between marking a call terminal and running its background completion, or a
    delivery that failed and released its claim, leaves ``notified_at`` NULL on a
    terminal row. ``complete_call`` claims each atomically, so this cannot double
    send a call another path is already handling.
    """
    cutoff = datetime.now(timezone.utc) - _LOOKBACK
    call_ids = (
        (
            await session.execute(
                select(Call.id)
                .where(
                    Call.status.in_(TERMINAL_STATUSES),
                    Call.notified_at.is_(None),
                    Call.created_at >= cutoff,
                )
                .order_by(Call.created_at)
                .limit(_MAX_CALLS_PER_PASS)
            )
        )
        .scalars()
        .all()
    )

    for call_id in call_ids:
        await complete_call(call_id, settings)
    return len(call_ids)
