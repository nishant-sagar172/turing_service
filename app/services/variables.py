"""Service layer for agent-variable resolution and validation.

Fetches an agent's config (read-only) and turns it into a required/optional
variable contract, then validates caller-supplied data against it.
"""

from __future__ import annotations

from app.config import Settings
from app.core.bolna_client import BolnaClient
from app.core.variables import (
    load_variable_overrides,
    resolve_agent_variables,
    validate_variables,
)


async def resolve_variables(
    client: BolnaClient, agent_id: str, settings: Settings
) -> dict[str, list[str]]:
    """Fetch the agent and return its required/optional variable contract."""
    agent = await client.get_agent(agent_id)
    overrides = load_variable_overrides(settings.agent_variables_file).get(
        agent_id, {}
    )
    return resolve_agent_variables(agent, overrides)


def check(provided: set[str], contract: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    """Return (missing_required, unrecognized_extra) for provided keys."""
    return validate_variables(provided, contract["required"], contract["optional"])
