"""Open portal lookup (/v1/portal/*).

POST /v1/portal/lookup — match active client by name + email, issue a fresh
portal-login key so clients can sign in without having their key to hand.

Both name AND email must match (case-insensitive); 404 is generic regardless
of which field failed so neither name nor email can be enumerated separately.
Only "active" clients succeed — pending/suspended are indistinguishable from
not-found.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Client
from app.db.session import get_session
from app.dependencies import get_redis
from app.schemas.admin import IssueKeyResponse
from app.services import rate_limit, tenants

router = APIRouter(prefix="/portal", tags=["portal"])

_NOT_FOUND = HTTPException(
    status_code=404,
    detail={
        "error": "not_found",
        "message": "No active account found for that name and email.",
    },
)


class PortalLookupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=1, max_length=256)


@router.post("/lookup", response_model=IssueKeyResponse)
async def portal_lookup(
    request: Request,
    body: PortalLookupRequest,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    redis: object = Depends(get_redis),
) -> IssueKeyResponse:
    ip = request.client.host if request.client else "unknown"
    if await rate_limit.hit(
        redis,
        bucket=f"portal:{ip}",
        limit=settings.register_rate_limit_per_hour,
        window_seconds=3600,
    ):
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limited",
                "message": "Too many attempts. Please try again later.",
            },
        )

    result = await session.execute(
        select(Client).where(
            func.lower(Client.name) == body.name.strip().lower(),
            func.lower(Client.contact_email) == body.email.strip().lower(),
            Client.status == "active",
        )
    )
    client = result.scalar_one_or_none()
    if client is None:
        raise _NOT_FOUND

    raw_key, key_row = await tenants.issue_key(session, client, label="portal-login")
    await session.commit()
    return IssueKeyResponse(key_id=key_row.id, api_key=raw_key)
