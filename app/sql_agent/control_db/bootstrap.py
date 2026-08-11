"""One-shot bootstrap for the SQL Builder Agent's dedicated control database.

Run as::

    python -m app.sql_agent.control_db.bootstrap

Idempotent: creates the database named in SQL_AGENT_CONTROL_DB_URL if missing
(connecting to the server's maintenance ``postgres`` DB), enables the pgvector
extension, then applies the schema via plain ``Base.metadata.create_all()`` —
deliberately no Alembic while this schema is still moving fast (spec §1).
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.sql_agent.config import get_sql_agent_settings
from app.sql_agent.control_db.models import EMBEDDING_DIM, Base

logger = logging.getLogger(__name__)

# CREATE DATABASE can't be parameterized, so the name is interpolated into the
# statement; restrict it to a safe identifier and fail closed on anything else.
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class BootstrapError(RuntimeError):
    """Raised when the control-DB bootstrap cannot proceed safely."""


async def _database_exists(conn: AsyncConnection, name: str) -> bool:
    result = await conn.execute(
        text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
    )
    return result.scalar() is not None


async def _ensure_database(control_db_url: str) -> str:
    """Create the control database on its server if missing; return its name."""
    url = make_url(control_db_url)
    db_name = url.database
    if not db_name:
        raise BootstrapError("SQL_AGENT_CONTROL_DB_URL has no database name.")
    if not _SAFE_IDENTIFIER.match(db_name):
        raise BootstrapError(
            f"Refusing to create database with unsafe name {db_name!r}; "
            "only [A-Za-z_][A-Za-z0-9_]* is accepted."
        )
    if db_name == "turing_db":
        raise BootstrapError(
            "SQL_AGENT_CONTROL_DB_URL points at turing_db; the SQL agent's "
            "control plane must use its own dedicated database."
        )

    admin_url = url.set(database="postgres")
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            if await _database_exists(conn, db_name):
                logger.info("Database %s already exists.", db_name)
            else:
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                logger.info("Created database %s.", db_name)
    finally:
        await admin_engine.dispose()
    return db_name


def _table_names(sync_conn_inspector: Inspector) -> list[str]:
    return sync_conn_inspector.get_table_names()


async def bootstrap() -> list[str]:
    """Ensure database + pgvector extension + schema. Returns table names."""
    settings = get_sql_agent_settings()
    if settings.sql_agent_embedding_dim != EMBEDDING_DIM:
        raise BootstrapError(
            f"SQL_AGENT_EMBEDDING_DIM={settings.sql_agent_embedding_dim} does not "
            f"match the models' fixed Vector width {EMBEDDING_DIM}. Changing "
            "dimension requires a coordinated migration + full re-embed; "
            "refusing to bootstrap a mismatched schema."
        )

    db_name = await _ensure_database(settings.sql_agent_control_db_url)

    engine = create_async_engine(settings.sql_agent_control_db_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
            tables = await conn.run_sync(lambda sync_conn: _table_names(inspect(sync_conn)))
    finally:
        await engine.dispose()

    logger.info("Bootstrap complete on %s; tables present: %s", db_name, sorted(tables))
    return sorted(tables)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        tables = asyncio.run(bootstrap())
    except BootstrapError as exc:
        logger.error("Bootstrap failed: %s", exc)
        return 1
    expected = sorted(Base.metadata.tables.keys())
    missing = [t for t in expected if t not in tables]
    if missing:
        logger.error("Bootstrap incomplete; missing tables: %s", missing)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
