"""Phone number catalog sync and per-client assignment.

Mirrors the agent_sync pattern: a local catalog is kept in sync with the voice
engine; operators then assign numbers to clients from that catalog.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.voice_engine import VoiceEngineClient
from app.db.models import ClientPhoneNumber, PhoneNumberCatalog

logger = logging.getLogger("turing.phone_number_sync")


async def sync_catalog(
    session: AsyncSession, client: VoiceEngineClient
) -> dict[str, int]:
    """Refresh ``phone_number_catalog`` from the voice engine."""
    numbers = await client.list_phone_numbers()
    now = datetime.now(timezone.utc)
    seen: set[str] = set()

    for item in numbers if isinstance(numbers, list) else []:
        if not isinstance(item, dict):
            continue
        item_d = cast(dict[str, Any], item)
        number = str(item_d.get("phone_number") or "").strip()
        if not number:
            continue
        seen.add(number)
        await _upsert(session, number, item_d, now)

    removed = await _mark_missing(session, seen, now)
    await session.flush()
    return {"synced": len(seen), "removed": removed}


async def _upsert(
    session: AsyncSession, phone_number: str, snapshot: dict[str, Any], now: datetime
) -> None:
    result = await session.execute(
        select(PhoneNumberCatalog).where(
            PhoneNumberCatalog.phone_number == phone_number
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = PhoneNumberCatalog(phone_number=phone_number)
        session.add(row)
    row.telephony_provider = snapshot.get("telephony_provider")
    row.rented = snapshot.get("rented")
    row.renewal_at = str(snapshot["renewal_at"]) if snapshot.get("renewal_at") else None
    row.is_present = True
    row.snapshot = snapshot
    row.last_synced_at = now


async def _mark_missing(session: AsyncSession, seen: set[str], now: datetime) -> int:
    result = await session.execute(
        select(PhoneNumberCatalog).where(PhoneNumberCatalog.is_present.is_(True))
    )
    count = 0
    for row in result.scalars().all():
        if row.phone_number not in seen:
            row.is_present = False
            row.last_synced_at = now
            count += 1
            logger.warning("Phone number removed from voice engine: %s", row.phone_number)
    return count


async def list_catalog(session: AsyncSession) -> list[PhoneNumberCatalog]:
    result = await session.execute(
        select(PhoneNumberCatalog).order_by(PhoneNumberCatalog.phone_number)
    )
    return list(result.scalars().all())


async def list_client_phone_numbers(
    session: AsyncSession, client_id: uuid.UUID
) -> list[tuple[ClientPhoneNumber, PhoneNumberCatalog]]:
    """Assigned + present numbers for a client."""
    result = await session.execute(
        select(ClientPhoneNumber, PhoneNumberCatalog)
        .join(
            PhoneNumberCatalog,
            ClientPhoneNumber.phone_number_id == PhoneNumberCatalog.id,
        )
        .where(
            ClientPhoneNumber.client_id == client_id,
            PhoneNumberCatalog.is_present.is_(True),
        )
        .order_by(PhoneNumberCatalog.phone_number)
    )
    return [(a, c) for a, c in result.all()]


async def get_assigned_numbers(
    session: AsyncSession, client_id: uuid.UUID
) -> list[str]:
    """E.164 strings for a client's assigned + present numbers."""
    pairs = await list_client_phone_numbers(session, client_id)
    return [cat.phone_number for _, cat in pairs]


async def set_client_phone_numbers(
    session: AsyncSession, client_id: uuid.UUID, phone_number_ids: list[uuid.UUID]
) -> None:
    """Replace the client's full assignment set."""
    result = await session.execute(
        select(ClientPhoneNumber).where(ClientPhoneNumber.client_id == client_id)
    )
    existing = {row.phone_number_id: row for row in result.scalars().all()}
    wanted = set(phone_number_ids)

    for pid, row in existing.items():
        if pid not in wanted:
            await session.delete(row)

    for pid in wanted - existing.keys():
        session.add(ClientPhoneNumber(client_id=client_id, phone_number_id=pid))

    await session.flush()


async def unknown_phone_number_ids(
    session: AsyncSession, phone_number_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    if not phone_number_ids:
        return []
    result = await session.execute(
        select(PhoneNumberCatalog.id).where(
            PhoneNumberCatalog.id.in_(phone_number_ids)
        )
    )
    known = {row for (row,) in result.all()}
    return [pid for pid in phone_number_ids if pid not in known]
