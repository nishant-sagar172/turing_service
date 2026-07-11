"""Persistence helpers for turing's batches/calls tables.

Centralizes the mapping from Bolna payloads to our rows so the create routers,
the webhook receiver, and the reconcile path all store data identically.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Batch, Call


def _telephony(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("telephony_data")
    return data if isinstance(data, dict) else {}


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
        recipient = ctx.get("recipient_data")
        if isinstance(recipient, dict):
            ref = recipient.get("patient_uhid")
            return str(ref) if ref is not None else None
    return None


def extract_bolna_batch_id(payload: dict[str, Any]) -> str | None:
    batch_run = payload.get("batch_run_details")
    if isinstance(batch_run, dict) and batch_run.get("batch_id"):
        return str(batch_run["batch_id"])
    if payload.get("batch_id"):
        return str(payload["batch_id"])
    return None


def _call_fields_from_execution(payload: dict[str, Any]) -> dict[str, Any]:
    tel = _telephony(payload)
    batch_run = payload.get("batch_run_details")
    retry_count = batch_run.get("retry_count") if isinstance(batch_run, dict) else None
    return {
        "status": payload.get("status") or "pending",
        "transcript": payload.get("transcript"),
        "recording_url": tel.get("recording_url"),
        "extracted_data": payload.get("extracted_data"),
        "cost": payload.get("total_cost"),
        "duration": payload.get("conversation_duration") or tel.get("duration"),
        "hangup_reason": tel.get("hangup_reason") or tel.get("hangup_by"),
        "retry_count": retry_count,
        "raw_payload": payload,
    }


async def record_single_call(
    session: AsyncSession,
    *,
    client: str | None,
    agent_id: str,
    contact_number: str,
    patient_ref: str | None,
    bolna_execution_id: str | None,
    status: str | None,
) -> Call:
    call = Call(
        client=client,
        agent_id=agent_id,
        contact_number=contact_number,
        patient_ref=patient_ref,
        bolna_execution_id=bolna_execution_id,
        status=status or "queued",
    )
    session.add(call)
    await session.flush()
    return call


async def record_batch(
    session: AsyncSession,
    *,
    client: str | None,
    agent_id: str,
    from_number: str | None,
    retry_config: dict[str, Any] | None,
    recipients: list[dict[str, Any]] | None,
    total_count: int,
    bolna_batch_id: str | None,
    status: str | None,
) -> Batch:
    batch = Batch(
        client=client,
        agent_id=agent_id,
        from_number=from_number,
        retry_config=retry_config,
        recipients_snapshot=recipients,
        total_count=total_count,
        bolna_batch_id=bolna_batch_id,
        status=status or "created",
    )
    session.add(batch)
    await session.flush()
    return batch


async def get_batch_by_bolna_id(
    session: AsyncSession, bolna_batch_id: str
) -> Batch | None:
    result = await session.execute(
        select(Batch).where(Batch.bolna_batch_id == bolna_batch_id)
    )
    return result.scalar_one_or_none()


async def get_call_by_execution_id(
    session: AsyncSession, execution_id: str
) -> Call | None:
    result = await session.execute(
        select(Call).where(Call.bolna_execution_id == execution_id)
    )
    return result.scalar_one_or_none()


async def upsert_call_from_execution(
    session: AsyncSession, payload: dict[str, Any]
) -> Call | None:
    """Create/update a Call row from a Bolna execution payload (webhook or
    executions listing). Idempotent on ``bolna_execution_id``."""
    execution_id = payload.get("id") or payload.get("execution_id")
    if not execution_id:
        return None
    execution_id = str(execution_id)

    call = await get_call_by_execution_id(session, execution_id)
    if call is None:
        batch = None
        bolna_batch_id = extract_bolna_batch_id(payload)
        if bolna_batch_id:
            batch = await get_batch_by_bolna_id(session, bolna_batch_id)
        call = Call(
            bolna_execution_id=execution_id,
            batch_id=batch.id if batch else None,
            client=batch.client if batch else None,
            agent_id=str(payload.get("agent_id") or (batch.agent_id if batch else "")),
            contact_number=extract_contact_number(payload),
            patient_ref=extract_patient_ref(payload),
        )
        session.add(call)

    for field, value in _call_fields_from_execution(payload).items():
        if value is not None:
            setattr(call, field, value)
    if call.contact_number is None:
        call.contact_number = extract_contact_number(payload)
    if call.patient_ref is None:
        call.patient_ref = extract_patient_ref(payload)

    await session.flush()
    return call


_SUCCESS_STATUSES = {"completed"}
_TERMINAL_STATUSES = {
    "completed", "no-answer", "busy", "failed", "canceled", "cancelled",
    "stopped", "error", "balance-low",
}


async def batch_metrics(session: AsyncSession, batch: Batch) -> dict[str, Any]:
    rows = await session.execute(
        select(Call.status, func.count(), func.coalesce(func.sum(Call.cost), 0.0),
               func.coalesce(func.avg(Call.duration), 0.0))
        .where(Call.batch_id == batch.id)
        .group_by(Call.status)
    )
    by_status: dict[str, int] = {}
    total_cost = 0.0
    weighted_duration = 0.0
    tracked = 0
    for status, count, cost_sum, avg_duration in rows:
        by_status[status] = count
        total_cost += float(cost_sum or 0)
        weighted_duration += float(avg_duration or 0) * count
        tracked += count

    completed = sum(by_status.get(s, 0) for s in _SUCCESS_STATUSES)
    terminal = sum(by_status.get(s, 0) for s in _TERMINAL_STATUSES)
    return {
        "batch_id": str(batch.id),
        "bolna_batch_id": batch.bolna_batch_id,
        "status": batch.status,
        "total_recipients": batch.total_count,
        "calls_tracked": tracked,
        "by_status": by_status,
        "completed": completed,
        "terminal": terminal,
        "success_rate": round(completed / terminal, 4) if terminal else None,
        "total_cost": round(total_cost, 4),
        "avg_duration_seconds": round(weighted_duration / tracked, 2) if tracked else None,
    }
