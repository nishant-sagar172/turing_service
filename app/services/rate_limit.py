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

log = logging.getLogger("turing.rate_limit")

# Fallback: in-process store mirrors the original register.py implementation.
_attempts: dict[str, list[float]] = {}


async def hit(
    redis,
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
            return await _redis_hit(redis, bucket=bucket, limit=limit, window_seconds=window_seconds)
        except Exception as exc:
            log.warning("rate_limit Redis error, falling back to in-memory: %s", exc)

    return _memory_hit(bucket=bucket, limit=limit, window_seconds=window_seconds)


async def _redis_hit(redis, *, bucket: str, limit: int, window_seconds: int) -> bool:
    key = f"turing:rl:{bucket}"
    async with redis.pipeline(transaction=False) as pipe:
        await pipe.incr(key)
        await pipe.expire(key, window_seconds)
        results = await pipe.execute()
    count = results[0]
    return count > limit


def _memory_hit(*, bucket: str, limit: int, window_seconds: int) -> bool:
    now = time.monotonic()
    window = _attempts.setdefault(bucket, [])
    window[:] = [t for t in window if now - t < window_seconds]
    if len(window) >= limit:
        return True
    window.append(now)
    return False
