"""FastAPI application entrypoint for turing_service.

API layout:
- ``/health``, ``/health/ready``          — open (liveness/readiness)
- ``/v1/*``                               — business surface, X-API-Key auth
- ``/webhooks/bolna``                     — Bolna callbacks, IP-allowlist auth

Every response carries ``X-Request-ID``; every error uses the standard
envelope ``{error, message, detail, request_id}`` (see app/errors.py).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app import __version__
from app.auth import require_api_key
from app.config import get_settings
from app.core.bolna_client import BolnaClient
from app.db.session import dispose_engine
from app.errors import register_error_handlers
from app.middleware import RequestContextMiddleware
from app.routers import (
    agents,
    batches,
    bolna,
    calls,
    health,
    phone_numbers,
    webhooks,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage process-wide resources: Bolna client + DB engine."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    logging.getLogger("turing_service").info(
        "Starting %s (env=%s) -> Bolna %s | DB %s",
        settings.app_name, settings.environment, settings.bolna_base_url,
        settings.database_url.split("@")[-1],
    )

    app.state.bolna_client = BolnaClient(
        api_key=settings.bolna_api_key,
        base_url=settings.bolna_base_url,
        timeout=settings.bolna_timeout_seconds,
    )
    try:
        yield
    finally:
        await app.state.bolna_client.aclose()
        await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="Standardized voice-calling micro-service over the Bolna API.",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    # Open endpoints.
    app.include_router(health.router)
    # Bolna push callbacks (source-IP checked inside the handler).
    app.include_router(webhooks.router)

    # Business surface: versioned under /v1, X-API-Key required.
    v1_auth = [Depends(require_api_key)]
    app.include_router(bolna.router, prefix="/v1", dependencies=v1_auth)
    app.include_router(calls.router, prefix="/v1", dependencies=v1_auth)
    app.include_router(batches.router, prefix="/v1", dependencies=v1_auth)
    app.include_router(phone_numbers.router, prefix="/v1", dependencies=v1_auth)
    app.include_router(agents.router, prefix="/v1", dependencies=v1_auth)

    return app


app = create_app()
