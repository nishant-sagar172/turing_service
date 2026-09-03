"""FastAPI dependencies — shared resources injected into route handlers.

Tenant/admin authentication itself happens in ``AuthMiddleware``
(app/middleware.py); these dependencies only *read* what the middleware
already established, so handlers get a typed tenant without re-deriving it.
"""

from typing import cast

from fastapi import HTTPException, Request

from app.auth import TenantContext
from app.core.voice_engine import VoiceEngineClient
from app.sql_agent.config import SqlAgentSettings
from app.sql_agent.config import get_sql_agent_settings as _get_sql_agent_settings


def get_voice_engine(request: Request) -> VoiceEngineClient:
    """Return the process-wide voice-engine client created during app startup."""
    return cast(VoiceEngineClient, request.app.state.voice_engine)


def get_current_tenant(request: Request) -> TenantContext:
    """Return the authenticated tenant attached by AuthMiddleware.

    Only reachable on routes AuthMiddleware has already gated, so ``tenant``
    is always present; the guard below is defense-in-depth, not the real gate.
    """
    tenant = getattr(request.state, "tenant", None)
    if tenant is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "message": "Missing or invalid X-API-Key.",
            },
        )
    return cast(TenantContext, tenant)


def get_redis(request: Request):
    """Return the process-wide async Redis client, or None when unconfigured."""
    return getattr(request.app.state, "redis", None)


def get_sql_agent_settings() -> SqlAgentSettings:
    return _get_sql_agent_settings()
