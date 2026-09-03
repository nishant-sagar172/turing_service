"""Lifecycle + persistence for clients (tenants): registration, admin
approval/rejection/suspension, API key issuance/rotation/revocation, and
per-client config.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import generate_api_key, invalidate_cache
from app.db.models import Batch, Call, Client, ClientApiKey, ClientConfig, RequestLog

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return slug or uuid.uuid4().hex[:8]


async def get_client_by_name(session: AsyncSession, name: str) -> Client | None:
    result = await session.execute(select(Client).where(Client.name == name))
    return result.scalar_one_or_none()


async def get_client(session: AsyncSession, client_id: uuid.UUID) -> Client | None:
    return await session.get(Client, client_id)


async def list_clients(
    session: AsyncSession, status: str | None = None
) -> list[Client]:
    stmt = select(Client).order_by(Client.created_at.desc())
    if status:
        stmt = stmt.where(Client.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def register_client(
    session: AsyncSession, *, name: str, contact_email: str | None
) -> Client:
    """Self-serve registration. A duplicate name returns the existing pending row."""
    existing = await get_client_by_name(session, name)
    if existing is not None:
        return existing
    client = Client(
        name=name,
        slug=_slugify(name),
        contact_email=contact_email,
        status="pending",
    )
    session.add(client)
    await session.flush()
    return client


async def admin_create_client(
    session: AsyncSession,
    *,
    name: str,
    contact_email: str | None,
    status: str = "pending",
) -> Client:
    """Admin-side create — raises ValueError if name already exists."""
    if await get_client_by_name(session, name) is not None:
        raise ValueError(f"Client '{name}' already exists.")
    client = Client(
        name=name,
        slug=_slugify(name),
        contact_email=contact_email,
        status=status,
    )
    session.add(client)
    await session.flush()
    return client


async def update_client(
    session: AsyncSession,
    client: Client,
    *,
    name: str | None = None,
    contact_email: str | None = None,
    clear_email: bool = False,
) -> Client:
    if name is not None and name != client.name:
        if await get_client_by_name(session, name) is not None:
            raise ValueError(f"Client '{name}' already exists.")
        client.name = name
        client.slug = _slugify(name)
    if clear_email:
        client.contact_email = None
    elif contact_email is not None:
        client.contact_email = contact_email
    await session.flush()
    return client


async def delete_client(session: AsyncSession, client: Client) -> None:
    # Batch and Call FKs have no DB-level cascade — delete them first.
    await session.execute(delete(Call).where(Call.client_id == client.id))
    await session.execute(delete(Batch).where(Batch.client_id == client.id))
    # request_logs.client_id has no ON DELETE cascade — null it out to preserve audit history.
    await session.execute(
        update(RequestLog)
        .where(RequestLog.client_id == client.id)
        .values(client_id=None)
    )
    await session.delete(client)
    invalidate_cache()


async def _issue_key(
    session: AsyncSession, client: Client, *, label: str | None
) -> tuple[str, ClientApiKey]:
    raw, prefix, digest = generate_api_key()
    key_row = ClientApiKey(
        client_id=client.id,
        key_hash=digest,
        key_prefix=prefix,
        label=label,
        status="active",
    )
    session.add(key_row)
    await session.flush()
    return raw, key_row


async def approve_client(
    session: AsyncSession, client: Client, *, approved_by: str
) -> tuple[Client, str]:
    """Activate a pending client and mint its first key.

    Returns ``(client, raw_key)`` — the raw key is shown to the caller once.
    """
    client.status = "active"
    client.approved_at = datetime.now(timezone.utc)
    client.approved_by = approved_by
    raw_key, _ = await _issue_key(session, client, label="initial")
    return client, raw_key


async def reject_client(client: Client) -> Client:
    client.status = "rejected"
    invalidate_cache()  # same as suspend: the client may have had active keys
    return client


async def suspend_client(client: Client) -> Client:
    client.status = "suspended"
    invalidate_cache()  # simplest correct option: drop the whole key cache
    return client


async def reactivate_client(client: Client) -> Client:
    client.status = "active"
    return client


async def issue_key(
    session: AsyncSession, client: Client, *, label: str | None
) -> tuple[str, ClientApiKey]:
    return await _issue_key(session, client, label=label)


async def get_key(
    session: AsyncSession, client_id: uuid.UUID, key_id: uuid.UUID
) -> ClientApiKey | None:
    result = await session.execute(
        select(ClientApiKey).where(
            ClientApiKey.id == key_id, ClientApiKey.client_id == client_id
        )
    )
    return result.scalar_one_or_none()


async def list_keys(session: AsyncSession, client_id: uuid.UUID) -> list[ClientApiKey]:
    result = await session.execute(
        select(ClientApiKey)
        .where(ClientApiKey.client_id == client_id)
        .order_by(ClientApiKey.created_at.desc())
    )
    return list(result.scalars().all())


def revoke_key(key: ClientApiKey) -> None:
    key.status = "revoked"
    invalidate_cache(key.key_hash)


async def get_config(
    session: AsyncSession, client_id: uuid.UUID
) -> ClientConfig | None:
    result = await session.execute(
        select(ClientConfig).where(ClientConfig.client_id == client_id)
    )
    return result.scalar_one_or_none()


async def get_or_create_config(
    session: AsyncSession, client_id: uuid.UUID
) -> ClientConfig:
    config = await get_config(session, client_id)
    if config is None:
        config = ClientConfig(client_id=client_id)
        session.add(config)
        await session.flush()
    return config


async def update_config(
    session: AsyncSession, client_id: uuid.UUID, **fields: Any
) -> ClientConfig:
    config = await get_or_create_config(session, client_id)
    for key, value in fields.items():
        setattr(
            config, key, value
        )  # None is intentional — explicit null clears the column
    await session.flush()
    return config
