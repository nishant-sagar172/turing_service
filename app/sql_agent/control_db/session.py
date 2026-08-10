"""Async SQLAlchemy engine/session for the SQL Builder Agent's control DB.

Completely separate from ``app.db.session``: different database
(sql_agent_db), different connection string (SQL_AGENT_CONTROL_DB_URL),
nothing shared. Created lazily so importing the module without the env var
set (e.g. for schema inspection) doesn't fail or open connections.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.sql_agent.config import get_sql_agent_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_control_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_sql_agent_settings().sql_agent_control_db_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
        )
    return _engine


def get_control_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_control_engine(), expire_on_commit=False
        )
    return _session_factory


async def get_control_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request; commit on success."""
    async with get_control_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_control_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
