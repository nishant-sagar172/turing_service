"""IP-based rate limiting for open endpoints (primarily POST /v1/register).

Primary: Redis INCR+EXPIRE sliding counter — durable across restarts and
shared across multiple uvicorn workers/replicas.

Fallback: in-process rolling timestamp window (same algorithm as the original
register.py implementation) — used automatically when Redis is None or raises.
The fallback is per-process and resets on restart; it is adequate for single-
worker deployments and makes registration fail-open during Redis downtime.

NOTE: ``bucket`` is the raw ``request.client.host`` string, which is only the
real client IP when uvicorn's ProxyHeadersMiddleware is configured with the
correct ``FORWARDED_ALLOW_IPS``. Setting that env var is the correct fix for
deployments behind a reverse proxy — do NOT parse X-Forwarded-For in app code.
"""

from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger("turing.rate_limit")

# Fallback: in-process store mirrors the original register.py implementation.
_attempts: dict[str, list[float]] = {}

# Upper bound on tracked buckets, so a flood of unique source IPs during a
# Redis outage cannot grow this dict without limit.
_MAX_BUCKETS = 10_000


async def hit(
    redis: Any,
    *,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> bool:
    """Record one attempt for ``bucket``.  Returns ``True`` if over limit."""
    if limit <= 0:
        return False

    if redis is not None:
        try:
            return await _redis_hit(
                redis, bucket=bucket, limit=limit, window_seconds=window_seconds
            )
        except Exception as exc:
            log.warning("rate_limit Redis error, falling back to in-memory: %s", exc)

    return _memory_hit(bucket=bucket, limit=limit, window_seconds=window_seconds)


async def _redis_hit(
    redis: Any, *, bucket: str, limit: int, window_seconds: int
) -> bool:
    key = f"turing:rl:{bucket}"
    async with redis.pipeline(transaction=False) as pipe:
        await pipe.incr(key)
        results = await pipe.execute()
    count = results[0]
    if count == 1:
        # Set TTL only on the first hit so the window expires naturally regardless
        # of ongoing traffic — resetting on every hit would lock out persistent
        # callers forever by preventing the key from ever expiring.
        await redis.expire(key, window_seconds)
    return count > limit


def _memory_hit(*, bucket: str, limit: int, window_seconds: int) -> bool:
    now = time.monotonic()
    _evict_stale(now, window_seconds)
    window = _attempts.setdefault(bucket, [])
    window[:] = [t for t in window if now - t < window_seconds]
    if len(window) >= limit:
        return True
    window.append(now)
    return False


def _evict_stale(now: float, window_seconds: float) -> None:
    """Drop buckets whose window has fully lapsed.

    Without this, every distinct source IP that ever hits an open endpoint
    leaks a dict entry for the life of the process — and this in-memory path is
    precisely the Redis-down fallback, i.e. the long-lived degraded case.
    """
    stale = [
        key
        for key, hits in _attempts.items()
        if not hits or now - hits[-1] >= window_seconds
    ]
    for key in stale:
        del _attempts[key]

    # Backstop: if a burst of unique buckets outpaces eviction, drop the
    # oldest-touched entries rather than growing without bound.
    if len(_attempts) > _MAX_BUCKETS:
        oldest = sorted(
            _attempts, key=lambda k: _attempts[k][-1] if _attempts[k] else 0.0
        )
        for key in oldest[: len(_attempts) - _MAX_BUCKETS]:
            del _attempts[key]
