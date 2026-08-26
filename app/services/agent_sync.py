"""Agent catalog sync + per-client enablement + drift detection.

Keeps ``agent_catalog`` as a local, queryable mirror of the voice engine's
agent list so client-scoped agent listing never has to call the engine live.
Drift = a client's *enabled* agent becoming unavailable upstream (removed, or
simply not returned anymore) — never a rename or status change.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.voice_engine import VoiceEngineClient
from app.db.models import AgentCatalog, AgentDriftEvent, ClientAgentConfig

logger = logging.getLogger("turing.agent_sync")


async def sync_catalog(
    session: AsyncSession, client: VoiceEngineClient
) -> dict[str, int]:
    """Refresh ``agent_catalog`` from the voice engine; detect + record drift."""
    agents = await client.list_agents()
    now = datetime.now(timezone.utc)
    seen_ids: set[str] = set()

    for item in agents if isinstance(agents, list) else []:
        if not isinstance(item, dict):
            continue
        item_d = cast(dict[str, Any], item)
        voice_agent_id = str(item_d.get("id") or "")
        if not voice_agent_id:
            continue
        seen_ids.add(voice_agent_id)
        await _upsert_agent(session, voice_agent_id, item_d, now)

    newly_missing = await _mark_missing(session, seen_ids, now)
    drift_events = await _detect_drift(session, newly_missing)
    await session.flush()
    return {
        "synced": len(seen_ids),
        "removed": len(newly_missing),
        "drift_events": drift_events,
    }


async def _upsert_agent(
    session: AsyncSession, voice_agent_id: str, snapshot: dict[str, Any], now: datetime,
) -> None:
    result = await session.execute(
        select(AgentCatalog).where(AgentCatalog.voice_agent_id == voice_agent_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = AgentCatalog(voice_agent_id=voice_agent_id)
        session.add(row)
    row.agent_name = snapshot.get("agent_name")
    row.agent_status = snapshot.get("agent_status")
    row.snapshot = snapshot
    row.is_present = True
    row.last_synced_at = now


async def _mark_missing(
    session: AsyncSession, seen_ids: set[str], now: datetime,
) -> list[str]:
    """Flag catalog rows the engine no longer returned. Returns their ids."""
    result = await session.execute(
        select(AgentCatalog).where(AgentCatalog.is_present.is_(True))
    )
    newly_missing: list[str] = []
    for row in result.scalars().all():
        if row.voice_agent_id not in seen_ids:
            row.is_present = False
            row.last_synced_at = now
            newly_missing.append(row.voice_agent_id)
    return newly_missing


async def _detect_drift(session: AsyncSession, newly_missing: list[str]) -> int:
    """Write agent_removed events for clients that had a missing agent enabled."""
    if not newly_missing:
        return 0
    result = await session.execute(
        select(ClientAgentConfig).where(
            ClientAgentConfig.voice_agent_id.in_(newly_missing),
            ClientAgentConfig.enabled.is_(True),
        )
    )
    count = 0
    for config in result.scalars().all():
        session.add(
            AgentDriftEvent(
                client_id=config.client_id,
                voice_agent_id=config.voice_agent_id,
                event_type="agent_removed",
                detail={"was_enabled": True},
            )
        )
        logger.warning(
            "Agent drift: voice_agent_id=%s removed upstream while enabled "
            "for client_id=%s", config.voice_agent_id, config.client_id,
        )
        count += 1
    return count


async def list_client_agents(
    session: AsyncSession, client_id: uuid.UUID
) -> list[tuple[ClientAgentConfig, AgentCatalog]]:
    """A client's enabled + still-present agents, catalog joined in."""
    result = await session.execute(
        select(ClientAgentConfig, AgentCatalog)
        .join(AgentCatalog,
              ClientAgentConfig.voice_agent_id == AgentCatalog.voice_agent_id)
        .where(
            ClientAgentConfig.client_id == client_id,
            ClientAgentConfig.enabled.is_(True),
            AgentCatalog.is_present.is_(True),
        )
    )
    return [(config, catalog) for config, catalog in result.all()]


async def is_agent_enabled(
    session: AsyncSession, client_id: uuid.UUID, voice_agent_id: str
) -> bool:
    result = await session.execute(
        select(ClientAgentConfig.enabled)
        .join(AgentCatalog,
              ClientAgentConfig.voice_agent_id == AgentCatalog.voice_agent_id)
        .where(
            ClientAgentConfig.client_id == client_id,
            ClientAgentConfig.voice_agent_id == voice_agent_id,
            ClientAgentConfig.enabled.is_(True),
            AgentCatalog.is_present.is_(True),
        )
    )
    return result.scalar_one_or_none() is True


async def set_client_agents(
    session: AsyncSession, client_id: uuid.UUID, voice_agent_ids: list[str],
) -> None:
    """Bulk-set a client's enabled agent ids (admin action) — replaces the set."""
    result = await session.execute(
        select(ClientAgentConfig).where(ClientAgentConfig.client_id == client_id)
    )
    existing = {row.voice_agent_id: row for row in result.scalars().all()}
    wanted = set(voice_agent_ids)

    for voice_agent_id, row in existing.items():
        row.enabled = voice_agent_id in wanted

    for voice_agent_id in wanted - existing.keys():
        session.add(
            ClientAgentConfig(
                client_id=client_id, voice_agent_id=voice_agent_id, enabled=True,
            )
        )


async def get_variable_overrides(
    session: AsyncSession, client_id: uuid.UUID, voice_agent_id: str
) -> dict[str, Any]:
    result = await session.execute(
        select(ClientAgentConfig.variable_overrides).where(
            ClientAgentConfig.client_id == client_id,
            ClientAgentConfig.voice_agent_id == voice_agent_id,
        )
    )
    overrides = result.scalar_one_or_none()
    return overrides if isinstance(overrides, dict) else {}


async def list_drift_events(
    session: AsyncSession, client_id: uuid.UUID
) -> list[AgentDriftEvent]:
    result = await session.execute(
        select(AgentDriftEvent)
        .where(AgentDriftEvent.client_id == client_id)
        .order_by(AgentDriftEvent.created_at.desc())
    )
    return list(result.scalars().all())


async def list_catalog(
    session: AsyncSession, *, include_missing: bool = True
) -> list[AgentCatalog]:
    """Full agent catalog for the admin surface — not filtered by client."""
    stmt = select(AgentCatalog).order_by(AgentCatalog.agent_name)
    if not include_missing:
        stmt = stmt.where(AgentCatalog.is_present.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_client_agent_config(
    session: AsyncSession, client_id: uuid.UUID,
) -> list[tuple[ClientAgentConfig, AgentCatalog | None]]:
    """All ClientAgentConfig rows for a client, LEFT-joined to the catalog.

    Returns drifted (catalog-missing) agents too so the admin can see and
    explicitly handle them rather than having them silently disappear.
    """
    result = await session.execute(
        select(ClientAgentConfig, AgentCatalog)
        .outerjoin(
            AgentCatalog,
            ClientAgentConfig.voice_agent_id == AgentCatalog.voice_agent_id,
        )
        .where(ClientAgentConfig.client_id == client_id)
        .order_by(AgentCatalog.agent_name)
    )
    return [(cfg, cat) for cfg, cat in result.all()]


async def unknown_agent_ids(
    session: AsyncSession, voice_agent_ids: list[str]
) -> list[str]:
    """Return which ids in ``voice_agent_ids`` are absent or missing from the catalog."""
    if not voice_agent_ids:
        return []
    result = await session.execute(
        select(AgentCatalog.voice_agent_id).where(
            AgentCatalog.voice_agent_id.in_(voice_agent_ids),
            AgentCatalog.is_present.is_(True),
        )
    )
    known = {row for (row,) in result.all()}
    return [aid for aid in voice_agent_ids if aid not in known]


async def update_client_agent_config(
    session: AsyncSession,
    client_id: uuid.UUID,
    voice_agent_id: str,
    *,
    display_name: str | None = None,
    variable_overrides: dict[str, Any] | None = None,
) -> ClientAgentConfig:
    """Upsert per-agent display_name / variable_overrides for one client."""
    result = await session.execute(
        select(ClientAgentConfig).where(
            ClientAgentConfig.client_id == client_id,
            ClientAgentConfig.voice_agent_id == voice_agent_id,
        )
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = ClientAgentConfig(
            client_id=client_id, voice_agent_id=voice_agent_id, enabled=False
        )
        session.add(cfg)
    if display_name is not None:
        cfg.display_name = display_name
    if variable_overrides is not None:
        cfg.variable_overrides = variable_overrides
    await session.flush()
    return cfg
