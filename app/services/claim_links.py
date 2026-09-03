"""One-time claim links: store a raw API key in Redis so the operator can
send a URL to the client and the client reveals it themselves.

Security model:
- Token is stored under ``hash_key(token)`` (SHA-256), not the raw token,
  so a Redis KEYS/SCAN/MONITOR exposure cannot reconstruct the URL.
- ``GETDEL`` atomically burns the value on first POST so the key is shown
  exactly once.
- GET (peek) is non-destructive — safe against Slack/Teams URL unfurlers
  that issue a HEAD/GET before the human clicks.
- TTL is a hard expiry backstop (default 24h); configure via
  ``settings.claim_link_ttl_hours``.
- Redis is started with ``--save "" --appendonly no`` so the key never
  reaches disk or a backup snapshot.

Fail-open: every function that touches Redis catches ``RedisError`` and
returns ``None`` so approve() still succeeds when Redis is down.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from app.auth import hash_key

log = logging.getLogger("turing.claim_links")

_NAMESPACE = "turing:claim:"


@dataclass(frozen=True)
class ClaimPeek:
    client_name: str
    expires_in_seconds: int


def _redis_key(token: str) -> str:
    return _NAMESPACE + hash_key(token)


async def create(
    redis: Any,
    *,
    client_id: uuid.UUID,
    client_name: str,
    raw_key: str,
    ttl_hours: float,
) -> str | None:
    """Mint a new claim token and store the key in Redis.

    Returns the plain token (to be embedded in the claim URL) or ``None`` if
    Redis is unavailable.
    """
    import secrets

    from redis.asyncio import Redis
    from redis.exceptions import RedisError

    if not isinstance(redis, Redis):
        return None

    token = secrets.token_urlsafe(32)
    payload = json.dumps(
        {
            "client_id": str(client_id),
            "client_name": client_name,
            "api_key": raw_key,
        }
    )
    ttl_seconds = int(ttl_hours * 3600)
    try:
        await redis.set(_redis_key(token), payload, ex=ttl_seconds)
        return token
    except RedisError as exc:
        log.warning("claim_links.create failed: %s", exc)
        return None


async def peek(redis: Any, token: str) -> ClaimPeek | None:
    """Non-destructive read: returns claim metadata or None if missing/expired."""
    from redis.asyncio import Redis
    from redis.exceptions import RedisError

    if not isinstance(redis, Redis):
        return None
    try:
        rk = _redis_key(token)
        raw = await redis.get(rk)
        if raw is None:
            return None
        ttl = await redis.ttl(rk)
        data = json.loads(raw)
        return ClaimPeek(
            client_name=data.get("client_name", ""),
            expires_in_seconds=max(int(ttl), 0),
        )
    except RedisError as exc:
        log.warning("claim_links.peek failed: %s", exc)
        return None


async def burn(redis: Any, token: str) -> tuple[str, str] | None:
    """Atomically consume the claim. Returns ``(client_name, raw_key)`` or None."""
    from redis.asyncio import Redis
    from redis.exceptions import RedisError

    if not isinstance(redis, Redis):
        return None
    try:
        raw = await redis.getdel(_redis_key(token))
        if raw is None:
            return None
        data = json.loads(raw)
        return data.get("client_name", ""), data["api_key"]
    except RedisError as exc:
        log.warning("claim_links.burn failed: %s", exc)
        return None


def build_claim_url(console_public_url: str, token: str) -> str:
    return f"{console_public_url.rstrip('/')}/claim/{token}"
