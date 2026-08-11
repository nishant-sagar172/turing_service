"""Tenant-scoped analytics endpoints (/v1/analytics/*).

All routes require X-API-Key (standard tenant auth). Admin-scoped mirrors
live under /v1/admin/clients/{id}/analytics/* in app/routers/admin.py and
reuse the same service functions.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext
from app.db.session import get_session
from app.dependencies import get_current_tenant
from app.schemas.analytics import (
    AgentStats,
    AnalyticsOverview,
    BatchStats,
    TimeseriesPoint,
)
from app.services import analytics as svc

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOverview)
async def overview(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    batch_id: uuid.UUID | None = Query(default=None),
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsOverview:
    return await svc.get_overview(
        session, tenant.client_id,
        date_from=date_from, date_to=date_to,
        agent_id=agent_id, batch_id=batch_id,
    )


@router.get("/by-agent", response_model=list[AgentStats])
async def by_agent(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    batch_id: uuid.UUID | None = Query(default=None),
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> list[AgentStats]:
    return await svc.get_by_agent(
        session, tenant.client_id,
        date_from=date_from, date_to=date_to, batch_id=batch_id,
    )


@router.get("/by-batch", response_model=list[BatchStats])
async def by_batch(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> list[BatchStats]:
    return await svc.get_by_batch(
        session, tenant.client_id,
        date_from=date_from, date_to=date_to, agent_id=agent_id,
    )


@router.get("/timeseries", response_model=list[TimeseriesPoint])
async def timeseries(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    batch_id: uuid.UUID | None = Query(default=None),
    granularity: str = Query(default="day", pattern="^(day|week)$"),
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> list[TimeseriesPoint]:
    return await svc.get_timeseries(
        session, tenant.client_id,
        date_from=date_from, date_to=date_to,
        agent_id=agent_id, batch_id=batch_id,
        granularity=granularity,
    )
