"""Service liveness/readiness endpoints (do not call Bolna)."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app import __version__
from app.config import Settings, get_settings
from app.db.session import get_session_factory
from app.schemas.common import HealthResponse

logger = logging.getLogger("turing.health")

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Return the service's own liveness state."""
    return HealthResponse(
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )


@router.get("/health/ready")
async def ready() -> dict:
    """Readiness: confirms the turing database is reachable.

    The session is opened here rather than injected so a connection failure
    becomes a 503 naming the failed dependency, instead of the generic 500 a
    dependency-resolution error produces. Container healthchecks probe this
    endpoint, so an unreachable database has to mark the service unhealthy.
    """
    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("Readiness check failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "database_unreachable",
                "message": "The turing database is not reachable.",
                "cause": type(exc).__name__,
            },
        ) from exc
    return {"status": "ready", "database": "ok"}
