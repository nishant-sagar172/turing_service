"""FastAPI application entrypoint for turing_service.

API layout:
- ``/health``, ``/health/ready``  — open (liveness/readiness)
- ``/v1/register``                — open (self-serve client registration)
- ``/v1/claim/*``                 — open (one-time API-key claim links)
- ``/v1/admin/*``                 — X-Admin-Key (operator surface)
- ``/v1/me/*``                    — X-API-Key (client self-serve portal)
- ``/v1/*``                       — business surface, X-API-Key (tenant-scoped)
- ``/webhooks/voice``             — voice-engine callbacks, IP-allowlist auth

Every response carries ``X-Request-ID``; every error uses the standard
envelope ``{error, message, detail, request_id}`` (see app/errors.py).
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.config import get_settings
from app.core.voice_engine import VoiceEngineClient
from app.db.session import dispose_engine, get_session_factory
from app.errors import register_error_handlers
from app.middleware import AuthMiddleware, RequestContextMiddleware
from app.routers import (
    admin,
    agents,
    analytics,
    batches,
    calls,
    claim,
    health,
    me,
    phone_numbers,
    portal,
    register,
    webhooks,
)
from app.services.agent_sync import sync_catalog

logger = logging.getLogger("turing_service")


async def _sync_loop(app: FastAPI, interval_minutes: float) -> None:
    interval = interval_minutes * 60
    while True:
        await asyncio.sleep(interval)
        try:
            async with get_session_factory()() as session:
                result = await sync_catalog(session, app.state.voice_engine)
                await session.commit()
                logger.info("Agent catalog sync: %s", result)
        except Exception:
            logger.exception("Agent catalog sync failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    logger.info(
        "Starting %s (env=%s) -> voice engine %s | DB %s",
        settings.app_name,
        settings.environment,
        settings.voice_engine_base_url,
        settings.database_url.split("@")[-1],
    )

    app.state.voice_engine = VoiceEngineClient(
        api_key=settings.voice_engine_api_key,
        base_url=settings.voice_engine_base_url,
        timeout=settings.voice_engine_timeout_seconds,
    )

    app.state.redis = None
    if settings.redis_url:
        try:
            import redis.asyncio as aioredis

            app.state.redis = aioredis.from_url(
                settings.redis_url, decode_responses=True
            )
            logger.info("Redis connected: %s", settings.redis_url.split("@")[-1])
        except Exception:
            logger.exception("Redis init failed — claim links disabled")

    sync_task: asyncio.Task[None] | None = None
    if settings.agent_sync_interval_minutes > 0:
        sync_task = asyncio.create_task(
            _sync_loop(app, settings.agent_sync_interval_minutes)
        )

    try:
        yield
    finally:
        if sync_task is not None:
            sync_task.cancel()
        await app.state.voice_engine.aclose()
        if app.state.redis is not None:
            await app.state.redis.aclose()
        await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="Multi-tenant voice-calling micro-service over a shared voice engine.",
        lifespan=lifespan,
    )

    # Starlette wraps outermost = most-recently added, so AuthMiddleware (added
    # first) ends up inner to RequestContextMiddleware (added second) — a
    # rejected request still carries a request id and gets logged.
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(webhooks.router)
    app.include_router(register.router, prefix="/v1")
    app.include_router(portal.router, prefix="/v1")
    app.include_router(claim.router, prefix="/v1")
    app.include_router(admin.router, prefix="/v1")
    app.include_router(me.router, prefix="/v1")

    app.include_router(calls.router, prefix="/v1")
    app.include_router(analytics.router, prefix="/v1")
    app.include_router(batches.router, prefix="/v1")
    app.include_router(phone_numbers.router, prefix="/v1")
    app.include_router(agents.router, prefix="/v1")

    try:
        from app.routers import sql_agent

        app.include_router(sql_agent.router, prefix="/v1")
    except Exception:
        logger.info("SQL Builder Agent disabled (dependencies not configured)")

    return app


app = create_app()
