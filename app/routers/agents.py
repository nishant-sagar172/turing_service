from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext
from app.config import Settings, get_settings
from app.core.voice_engine import VoiceEngineClient
from app.db.session import get_session
from app.dependencies import get_current_tenant, get_voice_engine
from app.schemas.agents import AgentSummary, AgentVariables, DriftEventResponse
from app.services import agent_sync
from app.services.variables import resolve_variables

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentSummary])
async def list_agents(
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> list[AgentSummary]:
    rows = await agent_sync.list_client_agents(session, tenant.client_id)
    return [
        AgentSummary(
            id=catalog.voice_agent_id,
            agent_name=config.display_name or catalog.agent_name,
            agent_status=catalog.agent_status,
            display_name=config.display_name,
        )
        for config, catalog in rows
    ]


@router.get("/drift", response_model=list[DriftEventResponse])
async def list_agent_drift(
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> list[DriftEventResponse]:
    """Agents that were enabled for this client but have since disappeared
    from the voice engine's catalog — i.e. calls to them would now fail."""
    events = await agent_sync.list_drift_events(session, tenant.client_id)
    return [
        DriftEventResponse(
            id=e.id,
            voice_agent_id=e.voice_agent_id,
            event_type=e.event_type,
            detail=e.detail,
            acknowledged=e.acknowledged,
            created_at=e.created_at,
        )
        for e in events
    ]


@router.get("/{agent_id}/variables", response_model=AgentVariables)
async def get_agent_variables(
    agent_id: str,
    tenant: TenantContext = Depends(get_current_tenant),
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> AgentVariables:
    if not await agent_sync.is_agent_enabled(session, tenant.client_id, agent_id):
        raise HTTPException(
            status_code=403,
            detail={"error": "agent_not_enabled",
                    "message": f"Agent '{agent_id}' is not enabled for this client."},
        )
    contract = await resolve_variables(
        voice_engine, agent_id, settings, session=session, client_id=tenant.client_id,
    )
    return AgentVariables(agent_id=agent_id, **contract)
