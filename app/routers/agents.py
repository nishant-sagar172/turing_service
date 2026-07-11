"""/agents endpoint — lists Bolna agents for the frontend agent picker."""

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.core.bolna_client import BolnaClient
from app.dependencies import get_bolna_client
from app.schemas.agents import AgentSummary, AgentVariables
from app.services.variables import resolve_variables

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentSummary])
async def list_agents(
    client: BolnaClient = Depends(get_bolna_client),
) -> list[AgentSummary]:
    """List all agents on the Bolna account (used to populate agent dropdowns)."""
    result = await client.list_agents()
    return [AgentSummary.model_validate(item) for item in result]


@router.get("/{agent_id}/variables", response_model=AgentVariables)
async def get_agent_variables(
    agent_id: str,
    client: BolnaClient = Depends(get_bolna_client),
    settings: Settings = Depends(get_settings),
) -> AgentVariables:
    """Discover (read-only) which variables the agent's prompt references.

    Frontends use this to render a dynamic input form per agent; callers use it
    to know exactly what to supply.
    """
    contract = await resolve_variables(client, agent_id, settings)
    return AgentVariables(agent_id=agent_id, **contract)
