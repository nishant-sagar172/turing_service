"""SQL Builder Agent API."""

from fastapi import APIRouter, Depends

from app.auth import TenantContext
from app.dependencies import get_current_tenant, get_sql_agent_settings
from app.sql_agent.config import SqlAgentSettings
from app.sql_agent.pipeline import build_query
from app.sql_agent.schemas import BuildQueryRequest, BuildQueryResponse

router = APIRouter(prefix="/sql-agent", tags=["sql-agent"])


@router.post("/query", response_model=BuildQueryResponse, status_code=200)
async def build_sql_query(
    body: BuildQueryRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    sql_settings: SqlAgentSettings = Depends(get_sql_agent_settings),
) -> BuildQueryResponse:
    return await build_query(
        body.question,
        workspace=body.workspace,
        settings=sql_settings,
        audit_client_id=tenant.client_id,
    )
