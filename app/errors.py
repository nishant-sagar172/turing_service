"""Standard error envelope for every turing error response.

Shape (always): ``{"error": <code>, "message": <human>, "detail": <any>,
"request_id": <id>}``. Structured HTTPException details (dicts carrying their
own ``error`` key, e.g. variable-validation 422s) are preserved in ``detail``.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.voice_engine import VoiceEngineError
from app.sql_agent.llm import LLMError

logger = logging.getLogger("turing.errors")


def _rid(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def envelope(request: Request, status_code: int, error: str, message: str,
             detail: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "message": message,
            "detail": detail,
            "request_id": _rid(request),
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(LLMError)
    async def _llm_error(request: Request, exc: LLMError) -> JSONResponse:
        return envelope(
            request,
            status_code=502,
            error="llm_error",
            message=str(exc),
            detail={"provider": exc.provider},
        )

    @app.exception_handler(VoiceEngineError)
    async def _voice_engine_error(request: Request, exc: VoiceEngineError) -> JSONResponse:
        # Upstream status passes through; transport failure -> 502.
        return envelope(
            request,
            status_code=exc.status_code or 502,
            error="voice_engine_error",
            message=str(exc),
            detail=exc.payload,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            # Structured error raised by our own code (e.g. missing variables).
            d = cast(dict[str, Any], detail)
            return envelope(
                request,
                status_code=exc.status_code,
                error=str(d.get("error")),
                message=str(d.get("message") or d.get("error")),
                detail=detail,
            )
        return envelope(
            request,
            status_code=exc.status_code,
            error="http_error",
            message=str(detail),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request,
                                exc: RequestValidationError) -> JSONResponse:
        return envelope(
            request,
            status_code=422,
            error="validation_error",
            message="Request validation failed.",
            detail=exc.errors(),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled error (request_id=%s)", _rid(request), exc_info=exc)
        return envelope(
            request,
            status_code=500,
            error="internal_error",
            message="Internal server error.",
        )
