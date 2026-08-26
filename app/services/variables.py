from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.variables import (
    load_variable_overrides,
    resolve_agent_variables,
    validate_variables,
)
from app.core.voice_engine import VoiceEngineClient
from app.services.agent_sync import get_variable_overrides


async def resolve_variables(
    client: VoiceEngineClient,
    agent_id: str,
    settings: Settings,
    *,
    session: AsyncSession | None = None,
    client_id: uuid.UUID | None = None,
) -> dict[str, list[str]]:
    agent = await client.get_agent(agent_id)
    overrides = load_variable_overrides(settings.agent_variables_file).get(agent_id, {})
    if session is not None and client_id is not None:
        per_client = await get_variable_overrides(session, client_id, agent_id)
        if per_client:
            overrides = per_client
    return resolve_agent_variables(agent, overrides)


def check(
    provided: set[str], contract: dict[str, list[str]]
) -> tuple[list[str], list[str]]:
    return validate_variables(provided, contract["required"], contract["optional"])
