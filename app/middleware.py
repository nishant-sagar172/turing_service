"""Request-ID/logging middleware and the tenant/admin auth gate.

Ordering (outermost -> innermost, see app/main.py):
1. ``RequestContextMiddleware`` — assigns X-Request-ID first, so even an auth
   rejection is logged with a request id.
2. ``AuthMiddleware`` — deny-by-default: every path is authenticated unless it
   is in the open allowlist or under ``/v1/admin`` (which uses X-Admin-Key
   instead). A route added without touching this file is still protected.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.auth import ClientInactiveError, admin_key_valid, resolve_api_key
from app.errors import envelope

logger = logging.getLogger("turing.requests")

# Paths that are noise in an audit log.
_SKIP_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/favicon")

# Strong references to in-flight request_logs writes; see RequestContextMiddleware.
_background_tasks: set[asyncio.Task[None]] = set()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()

        response = await call_next(request)

        latency_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id

        path = request.url.path
        if not path.startswith(_SKIP_PREFIXES):
            # The loop keeps only a weak reference to a bare create_task, so the
            # task can be garbage-collected before it runs and the request_logs
            # insert vanishes with no error anywhere. Hold a strong reference
            # until it completes.
            task = asyncio.create_task(
                self._record(request, response.status_code, latency_ms, request_id)
            )
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
        return response

    async def _record(
        self, request: Request, status_code: int, latency_ms: float, request_id: str
    ) -> None:
        """Best-effort insert into request_logs; never raises."""
        try:
            from app.db.models import RequestLog
            from app.db.session import get_session_factory

            tenant = getattr(request.state, "tenant", None)
            path = request.url.path
            # Redact claim tokens — they contain embedded credentials.
            if path.startswith("/v1/claim/"):
                path = "/v1/claim/<redacted>"
            async with get_session_factory()() as session:
                session.add(
                    RequestLog(
                        request_id=request_id,
                        client_id=tenant.client_id if tenant else None,
                        method=request.method,
                        endpoint=path,
                        status_code=status_code,
                        latency_ms=round(latency_ms, 2),
                    )
                )
                await session.commit()
        except Exception as exc:
            logger.debug("request_logs insert skipped: %s", exc)


# The only unauthenticated paths. Everything else is denied by default.
_OPEN_PATHS = frozenset(
    {
        "/health",
        "/health/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/v1/register",
        "/webhooks/voice",
        "/v1/portal/lookup",
    }
)
# Prefix-matched open paths (startswith check — covers dynamic segments).
# /v1/claim/{token}: open so clients can reveal their key without an API key.
_OPEN_PREFIXES: tuple[str, ...] = ("/v1/claim/",)
_ADMIN_PREFIX = "/v1/admin"


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        if path in _OPEN_PATHS or path.startswith(_OPEN_PREFIXES):
            return await call_next(request)

        if path.startswith(_ADMIN_PREFIX):
            if not admin_key_valid(request):
                return self._deny(
                    request, 403, "forbidden", "Missing or invalid X-Admin-Key."
                )
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return self._deny(request, 401, "unauthorized", "Missing X-API-Key.")

        from app.db.session import get_session_factory

        try:
            async with get_session_factory()() as session:
                tenant = await resolve_api_key(session, api_key)
        except ClientInactiveError:
            return self._deny(request, 403, "forbidden", "Client is not active.")

        if tenant is None:
            return self._deny(request, 401, "unauthorized", "Invalid X-API-Key.")

        request.state.tenant = tenant
        return await call_next(request)

    @staticmethod
    def _deny(
        request: Request, status_code: int, error: str, message: str
    ) -> JSONResponse:
        return envelope(request, status_code, error, message)
