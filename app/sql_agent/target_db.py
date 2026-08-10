"""Read-only async engine/session manager for a workspace's target database.

The target DB (e.g. Kalaam's Postgres) holds production data this agent must
never mutate. Defense in depth (plan §6): the server-side role is SELECT-only,
and every connection made here additionally forces
``default_transaction_read_only=on`` plus a ``statement_timeout``. This module
is deliberately independent of ``app/db/session.py`` — nothing is shared with
turing's own database plumbing.

Connections are resolved from an *environment-variable name* (e.g.
``KALAAM_READONLY_DATABASE_URL``), matching the control-plane design where
``sql_agent_datasources.connection_env_var`` stores the name, never the
credential.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import os

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DEFAULT_STATEMENT_TIMEOUT_MS = 10_000

_ASYNC_DRIVER = "postgresql+asyncpg"

_engines: dict[str, AsyncEngine] = {}


class TargetDBConfigError(RuntimeError):
    """A target-DB connection could not be built from the environment."""


def _build_url(connection_env_var: str) -> URL:
    raw = os.environ.get(connection_env_var, "").strip()
    if not raw:
        raise TargetDBConfigError(
            f"Environment variable {connection_env_var!r} is not set; it must "
            "hold the read-only connection URL for the workspace's target DB."
        )
    url = make_url(raw)
    if url.drivername in ("postgresql", "postgres"):
        url = url.set(drivername=_ASYNC_DRIVER)
    if url.drivername != _ASYNC_DRIVER:
        raise TargetDBConfigError(
            f"{connection_env_var} must be a {_ASYNC_DRIVER} URL "
            f"(got driver {url.drivername!r}); target-DB access is Postgres-only."
        )
    return url


def get_target_engine(
    connection_env_var: str,
    *,
    statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
) -> AsyncEngine:
    """Return (and cache, keyed by env-var name) a read-only engine.

    ``statement_timeout_ms`` is applied when the engine is first created; later
    calls for the same env var reuse the cached engine unchanged.
    """
    if statement_timeout_ms <= 0:
        raise TargetDBConfigError("statement_timeout_ms must be positive (fail closed).")
    engine = _engines.get(connection_env_var)
    if engine is None:
        engine = create_async_engine(
            _build_url(connection_env_var),
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=3,
            connect_args={
                "server_settings": {
                    "default_transaction_read_only": "on",
                    "statement_timeout": str(statement_timeout_ms),
                },
            },
        )
        _engines[connection_env_var] = engine
    return engine


@asynccontextmanager
async def target_session(
    connection_env_var: str,
    *,
    statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
) -> AsyncIterator[AsyncSession]:
    """Read-only session against a workspace's target DB.

    Never commits — every transaction ends in rollback, which is a no-op for
    the read-only work this agent does and guarantees nothing is ever persisted
    even if a write somehow slipped past every other guard.
    """
    engine = get_target_engine(
        connection_env_var, statement_timeout_ms=statement_timeout_ms
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


async def dispose_target_engines() -> None:
    """Dispose every cached target-DB engine (shutdown / test teardown)."""
    engines = list(_engines.values())
    _engines.clear()
    for engine in engines:
        await engine.dispose()
