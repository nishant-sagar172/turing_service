"""Self-serve client registration (/v1/register).

Open endpoint — listed in middleware._OPEN_PATHS (exact match).
Creates a ``pending`` client row; no key is issued until an admin approves.

Rate limiting: delegates to services/rate_limit which prefers a Redis INCR
counter (durable, shared across workers) and falls back to an in-process
rolling window.  The bucket is ``request.client.host``; deployments behind
a reverse proxy must set ``FORWARDED_ALLOW_IPS`` so uvicorn resolves the real
client IP rather than the proxy IP.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.session import get_session
from app.dependencies import get_redis
from app.schemas.clients import RegisterRequest, RegisterResponse
from app.services import rate_limit
from app.services.tenants import register_client

router = APIRouter(prefix="/register", tags=["register"])


@router.post("", response_model=RegisterResponse, status_code=201)
async def register(
    request: Request,
    body: RegisterRequest,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    redis=Depends(get_redis),
) -> RegisterResponse:
    ip = request.client.host if request.client else "unknown"
    if await rate_limit.hit(
        redis,
        bucket=ip,
        limit=settings.register_rate_limit_per_hour,
        window_seconds=3600,
    ):
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limited",
                "message": "Too many registration attempts. Please try again later.",
            },
        )
    await register_client(session, name=body.name, contact_email=body.contact_email)
    return RegisterResponse(
        status="pending",
        message="Registration received. An operator will review your application and send your credentials.",
    )
