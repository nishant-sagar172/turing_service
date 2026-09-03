"""Tenant API-key authentication: key issuance, hashing, verification, cache.

Every client request carries ``X-API-Key`` (stateless — resolved fresh each
request, no sessions). The raw key is never stored: only a SHA-256 hash plus a
short, non-secret prefix used to narrow the DB lookup before a constant-time
comparison. A short-TTL in-memory cache avoids a DB round-trip per request;
see ``api_key_cache_ttl_seconds`` for the accepted revocation-lag tradeoff.

Admin access (``X-Admin-Key``) is a separate, session-less, DB-less check
against the env-seeded ``ADMIN_API_KEY``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Client, ClientApiKey

_KEY_PREFIX_CHARS = 11  # "tk_" + 8 chars — enough to narrow a lookup, not secret


@dataclass(frozen=True)
class TenantContext:
    """Identity of the authenticated caller, attached to ``request.state.tenant``."""

    client_id: uuid.UUID
    name: str
    status: str


class ClientInactiveError(Exception):
    """The presented key is valid but its owning client is not active (-> 403)."""


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Create a new key. Returns ``(raw_key, key_prefix, key_hash)``.

    The raw value is returned to the caller exactly once (at issuance); only
    ``key_prefix``/``key_hash`` are persisted.
    """
    raw = "tk_" + secrets.token_urlsafe(32)
    return raw, raw[:_KEY_PREFIX_CHARS], hash_key(raw)


def admin_key_valid(request: Request) -> bool:
    """Constant-time check of ``X-Admin-Key`` against the configured admin key.

    Compares bytes to avoid TypeError on non-ASCII header values (latin-1
    decoded by Starlette), which would raise inside middleware and produce a
    bare 500 without an error envelope.
    """
    presented = request.headers.get("X-Admin-Key")
    if not presented:
        return False
    return hmac.compare_digest(
        presented.encode("utf-8"),
        get_settings().admin_api_key.encode("utf-8"),
    )


# ── Short-TTL cache: key_hash -> (tenant, expires_at) ───────────────────────
_cache: dict[str, tuple[TenantContext, float]] = {}


def _cache_get(key_hash: str) -> TenantContext | None:
    entry = _cache.get(key_hash)
    if entry is None:
        return None
    tenant, expires_at = entry
    if time.monotonic() >= expires_at:
        _cache.pop(key_hash, None)
        return None
    return tenant


def _cache_put(key_hash: str, tenant: TenantContext) -> None:
    ttl = get_settings().api_key_cache_ttl_seconds
    _cache[key_hash] = (tenant, time.monotonic() + ttl)


def invalidate_cache(key_hash: str | None = None) -> None:
    """Evict one cached key (on rotate/revoke/suspend) or the whole cache."""
    if key_hash is None:
        _cache.clear()
    else:
        _cache.pop(key_hash, None)


async def resolve_api_key(session: AsyncSession, raw_key: str) -> TenantContext | None:
    """Resolve ``X-API-Key`` to a tenant.

    Returns ``None`` if no active key matches (caller maps this to 401).
    Raises ``ClientInactiveError`` if the key is valid but its client is not
    active (caller maps this to 403).
    """
    digest = hash_key(raw_key)
    cached = _cache_get(digest)
    if cached is not None:
        return cached

    prefix = raw_key[:_KEY_PREFIX_CHARS]
    result = await session.execute(
        select(ClientApiKey, Client)
        .join(Client, ClientApiKey.client_id == Client.id)
        .where(ClientApiKey.key_prefix == prefix, ClientApiKey.status == "active")
    )
    for api_key_row, client in result.all():
        if not hmac.compare_digest(api_key_row.key_hash, digest):
            continue
        if client.status != "active":
            raise ClientInactiveError(client.status)
        tenant = TenantContext(
            client_id=client.id, name=client.name, status=client.status
        )
        api_key_row.last_used_at = datetime.now(timezone.utc)
        await session.commit()
        _cache_put(digest, tenant)
        return tenant
    return None
