"""Request-ID + request-logging middleware.

Every response carries ``X-Request-ID``. Business requests are recorded in the
``request_logs`` table (best-effort — logging failures never break a request).
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("turing.requests")

# Paths that are noise in an audit log.
_SKIP_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/favicon")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()

        response = await call_next(request)

        latency_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id

        path = request.url.path
        if not path.startswith(_SKIP_PREFIXES):
            await self._record(request, response.status_code, latency_ms, request_id)
        return response

    async def _record(self, request: Request, status_code: int,
                      latency_ms: float, request_id: str) -> None:
        """Best-effort insert into request_logs; never raises."""
        try:
            from app.db.models import RequestLog
            from app.db.session import get_session_factory

            async with get_session_factory()() as session:
                session.add(
                    RequestLog(
                        request_id=request_id,
                        client=getattr(request.state, "api_client", None),
                        method=request.method,
                        endpoint=request.url.path,
                        status_code=status_code,
                        latency_ms=round(latency_ms, 2),
                    )
                )
                await session.commit()
        except Exception as exc:
            logger.debug("request_logs insert skipped: %s", exc)
