"""Client self-serve portal endpoints (/v1/me/*).

All routes require X-API-Key (enforced by AuthMiddleware) and operate on the
authenticated tenant's own data only.  Clients cannot cross-read or modify
another tenant's records — ``client_id`` is always sourced from
``get_current_tenant()``, never from a path parameter.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext
from app.db.models import Client, ClientApiKey
from app.db.session import get_session
from app.dependencies import get_current_tenant
from app.schemas.admin import ClientConfigResponse, IssueKeyRequest, IssueKeyResponse, KeySummary
from app.schemas.me import MeResponse
from app.services import tenants

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeResponse)
async def get_me(
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    client = await session.get(Client, tenant.client_id)
    if client is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Client not found."})

    keys = await tenants.list_keys(session, tenant.client_id)
    active_count = sum(1 for k in keys if k.status == "active")
    return MeResponse(
        client_id=client.id,
        name=client.name,
        slug=client.slug,
        contact_email=client.contact_email,
        status=client.status,
        created_at=client.created_at,
        approved_at=client.approved_at,
        active_key_count=active_count,
    )


@router.get("/config", response_model=ClientConfigResponse)
async def get_my_config(
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> ClientConfigResponse:
    config = await tenants.get_config(session, tenant.client_id)
    if config is None:
        return ClientConfigResponse(
            default_from_number=None,
            webhook_url=None,
            webhook_secret_set=False,
            visible_fields=None,
            settings=None,
        )
    return ClientConfigResponse(
        default_from_number=config.default_from_number,
        webhook_url=config.webhook_url,
        webhook_secret_set=bool(config.webhook_secret),
        visible_fields=config.visible_fields,
        settings=config.settings,
    )


@router.get("/keys", response_model=list[KeySummary])
async def list_my_keys(
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> list[KeySummary]:
    return await tenants.list_keys(session, tenant.client_id)


@router.post("/keys", response_model=IssueKeyResponse, status_code=201)
async def issue_my_key(
    body: IssueKeyRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> IssueKeyResponse:
    client = await session.get(Client, tenant.client_id)
    if client is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Client not found."})
    raw_key, key_row = await tenants.issue_key(session, client, label=body.label)
    return IssueKeyResponse(key_id=key_row.id, api_key=raw_key)


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_my_key(
    key_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> None:
    key = await tenants.get_key(session, tenant.client_id, key_id)
    if key is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"No key with id '{key_id}'."},
        )
    tenants.revoke_key(key)
