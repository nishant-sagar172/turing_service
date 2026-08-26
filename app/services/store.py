"""Persistence helpers for turing's batches/calls tables.

Centralizes the mapping from voice-engine payloads to our rows so the create
routers, the webhook receiver, and the reconcile path all store data
identically.

Isolation (query layer): every client-facing lookup takes ``client_id`` and
filters on it — there is no way to fetch another tenant's row through these
functions. The two ``*_global`` lookups are the sole exception, used only by
the inbound webhook (which authenticates via IP allowlist, not a tenant key,
and must resolve *which* tenant owns an incoming execution before anything
else can be scoped).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.call_status import CONNECTED_STATUSES as _SUCCESS_STATUSES
from app.core.call_status import TERMINAL_STATUSES
from app.db.models import Batch, Call

logger = logging.getLogger("turing.store")


def _telephony(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("telephony_data")
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    return {}


def extract_contact_number(payload: dict[str, Any]) -> str | None:
    tel = _telephony(payload)
    return (
        tel.get("to_number")
        or payload.get("user_number")
        or payload.get("recipient_phone_number")
    )


def extract_patient_ref(payload: dict[str, Any]) -> str | None:
    ctx = payload.get("context_details")
    if isinstance(ctx, dict):
        ctx_d = cast(dict[str, Any], ctx)
        recipient = ctx_d.get("recipient_data")
        if isinstance(recipient, dict):
            ref = cast(dict[str, Any], recipient).get("patient_uhid")
            return str(ref) if ref is not None else None
    return None


def extract_voice_batch_id(payload: dict[str, Any]) -> str | None:
    batch_run = payload.get("batch_run_details")
    if isinstance(batch_run, dict):
        br = cast(dict[str, Any], batch_run)
        if br.get("batch_id"):
            return str(br["batch_id"])
    if payload.get("batch_id"):
        return str(payload["batch_id"])
    return None


def _coerce_cost(payload: dict[str, Any]) -> float | None:
    """Convert the upstream ``total_cost`` (minor units) to a major-unit float.

    The payload is untrusted vendor input, so the type is checked rather than
    assumed: a string or other non-numeric value must not raise, because this
    mapping runs per-item inside the reconcile loop and one malformed record
    would otherwise abort every remaining call in the pass. ``bool`` is
    rejected explicitly — it is an ``int`` subclass, so ``True / 100`` would
    silently record a cost of 0.01.
    """
    raw = payload.get("total_cost")
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        logger.warning(
            "ignoring non-numeric total_cost %r (%s) for execution %s",
            raw,
            type(raw).__name__,
            payload.get("id"),
        )
        return None
    return raw / 100


def _call_fields_from_execution(payload: dict[str, Any]) -> dict[str, Any]:
    tel = _telephony(payload)
    batch_run = payload.get("batch_run_details")
    batch_run_d = cast(dict[str, Any], batch_run) if isinstance(batch_run, dict) else None
    retry_count = batch_run_d.get("retry_count") if batch_run_d is not None else None
    cost = _coerce_cost(payload)
    return {
        "status": payload.get("status") or "pending",
        "transcript": payload.get("transcript"),
        "recording_url": tel.get("recording_url"),
        "extracted_data": payload.get("extracted_data"),
        "cost": cost,
        # Dual-write integer minor units (B-10). `cost` stays authoritative
        # until analytics readers migrate off the float column.
        "cost_cents": None if cost is None else round(cost * 100),
        "duration": payload.get("conversation_duration") or tel.get("duration"),
        "hangup_reason": tel.get("hangup_reason") or tel.get("hangup_by"),
        "retry_count": retry_count,
        "raw_payload": payload,
    }


async def record_call(
    session: AsyncSession,
    *,
    client_id: uuid.UUID,
    agent_id: str,
    voice_call_id: str,
    contact_number: str | None,
    status: str = "queued",
) -> Call:
    """Seed an initial Call row for a single (non-batch) outbound call.

    Idempotent: DO NOTHING on the unique constraint, then re-read so a webhook
    that races the placement response doesn't lose its update.
    """
    await session.execute(
        pg_insert(Call)
        .values(
            client_id=client_id,
            agent_id=agent_id,
            voice_call_id=voice_call_id,
            contact_number=contact_number,
            status=status,
        )
        .on_conflict_do_nothing(constraint="uq_call_client_voice_id")
    )
    call = await get_call_by_voice_id(session, client_id, voice_call_id)
    if call is None:
        logger.warning("call row for execution %s not visible after insert", voice_call_id)
        raise RuntimeError(f"Call row for {voice_call_id} not visible after insert")
    return call


async def record_batch(
    session: AsyncSession,
    *,
    client_id: uuid.UUID,
    agent_id: str,
    from_number: str | None,
    retry_config: dict[str, Any] | None,
    recipients: list[dict[str, Any]] | None,
    total_count: int,
    voice_batch_id: str | None,
    status: str | None,
) -> Batch:
    batch = Batch(
        client_id=client_id,
        agent_id=agent_id,
        from_number=from_number,
        retry_config=retry_config,
        recipients_snapshot=recipients,
        total_count=total_count,
        voice_batch_id=voice_batch_id,
        status=status or "created",
    )
    session.add(batch)
    await session.flush()
    return batch


async def get_batch_by_voice_id(
    session: AsyncSession, client_id: uuid.UUID, voice_batch_id: str
) -> Batch | None:
    """Tenant-scoped lookup — the only kind client-facing routes may use."""
    result = await session.execute(
        select(Batch).where(
            Batch.client_id == client_id, Batch.voice_batch_id == voice_batch_id
        )
    )
    return result.scalar_one_or_none()


async def get_call_by_voice_id(
    session: AsyncSession, client_id: uuid.UUID, voice_call_id: str
) -> Call | None:
    """Tenant-scoped lookup — the only kind client-facing routes may use."""
    result = await session.execute(
        select(Call).where(
            Call.client_id == client_id, Call.voice_call_id == voice_call_id
        )
    )
    return result.scalar_one_or_none()


async def get_batch_by_voice_id_global(
    session: AsyncSession, voice_batch_id: str
) -> Batch | None:
    """Unscoped lookup for the inbound webhook, which has no tenant key yet."""
    result = await session.execute(
        select(Batch).where(Batch.voice_batch_id == voice_batch_id)
    )
    return result.scalar_one_or_none()


async def get_call_by_voice_id_global(
    session: AsyncSession, voice_call_id: str
) -> Call | None:
    """Unscoped lookup for the inbound webhook, which has no tenant key yet."""
    result = await session.execute(
        select(Call).where(Call.voice_call_id == voice_call_id)
    )
    return result.scalar_one_or_none()


async def upsert_call_from_execution(
    session: AsyncSession,
    payload: dict[str, Any],
    *,
    client_id: uuid.UUID | None = None,
) -> Call | None:
    """Create/update a Call row from a voice-engine execution payload.

    Idempotent on ``voice_call_id``. When the call doesn't exist yet, its
    tenant is either the given ``client_id`` (batch-executions reconcile,
    where the batch is already tenant-verified) or resolved from the owning
    batch (inbound webhook, which knows no tenant in advance). If neither is
    available, the execution cannot be attributed to a tenant and is dropped.
    """
    execution_id = payload.get("id") or payload.get("execution_id")
    if not execution_id:
        return None
    execution_id = str(execution_id)

    call = await get_call_by_voice_id_global(session, execution_id)
    if call is None:
        resolved_client_id = client_id
        batch = None
        voice_batch_id = extract_voice_batch_id(payload)
        if voice_batch_id:
            batch = await get_batch_by_voice_id_global(session, voice_batch_id)
            if batch is not None:
                resolved_client_id = batch.client_id
        if resolved_client_id is None:
            return None

        # Insert-or-nothing, then re-read. Two concurrent deliveries for the same
        # execution (a webhook retry racing the reconcile poll) would both see
        # None above and both INSERT; the loser's IntegrityError would propagate
        # and abort every remaining item in the enclosing reconcile loop.
        #
        # DO NOTHING rather than DO UPDATE on purpose: the field updates below
        # already skip None values, so a sparse later payload cannot null out
        # columns an earlier richer one populated. A DO UPDATE SET built from the
        # raw payload would lose that protection.
        await session.execute(
            pg_insert(Call)
            .values(
                client_id=resolved_client_id,
                voice_call_id=execution_id,
                batch_id=batch.id if batch else None,
                agent_id=str(payload.get("agent_id") or (batch.agent_id if batch else "")),
                contact_number=extract_contact_number(payload),
                patient_ref=extract_patient_ref(payload),
            )
            .on_conflict_do_nothing(constraint="uq_call_client_voice_id")
        )
        call = await get_call_by_voice_id_global(session, execution_id)
        if call is None:
            # Lost the race and the winner's row is not visible in this
            # transaction — safe to skip; the next reconcile pass will update it.
            logger.warning("call row for execution %s not visible after upsert", execution_id)
            return None

    for field, value in _call_fields_from_execution(payload).items():
        if value is not None:
            setattr(call, field, value)
    if call.contact_number is None:
        call.contact_number = extract_contact_number(payload)
    if call.patient_ref is None:
        call.patient_ref = extract_patient_ref(payload)

    await session.flush()
    return call


async def batch_metrics(session: AsyncSession, batch: Batch) -> dict[str, Any]:
    rows = await session.execute(
        select(Call.status, func.count(), func.coalesce(func.sum(Call.cost), 0.0),
               func.coalesce(func.sum(Call.duration), 0.0), func.count(Call.duration))
        .where(Call.batch_id == batch.id)
        .group_by(Call.status)
    )
    by_status: dict[str, int] = {}
    total_cost = 0.0
    total_duration = 0.0
    duration_count = 0
    tracked = 0
    for status, count, cost_sum, dur_sum, dur_count in rows:
        by_status[status] = count
        total_cost += float(cost_sum or 0)
        total_duration += float(dur_sum or 0)
        duration_count += int(dur_count or 0)
        tracked += count

    completed = sum(by_status.get(s, 0) for s in _SUCCESS_STATUSES)
    terminal = sum(by_status.get(s, 0) for s in TERMINAL_STATUSES)
    return {
        "batch_id": str(batch.id),
        "voice_batch_id": batch.voice_batch_id,
        "status": batch.status,
        "total_recipients": batch.total_count,
        "calls_tracked": tracked,
        "by_status": by_status,
        "completed": completed,
        "terminal": terminal,
        "success_rate": round(completed / terminal, 4) if terminal else None,
        "total_cost": round(total_cost, 4),
        "avg_duration_seconds": round(total_duration / duration_count, 2) if duration_count else None,
    }
