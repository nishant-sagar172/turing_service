"""Service-to-service authentication for turing's business endpoints.

Consumers (e.g. the Kalaam backend) present a shared secret in ``X-API-Key``.
Keys are configured via ``TURING_API_KEYS`` (comma-separated).
"""

from __future__ import annotations

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from app.config import get_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _client_label(key: str) -> str:
    """Non-secret label for logs: first 6 chars of the key."""
    return f"key-{key[:6]}"


async def require_api_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> str:
    """Validate X-API-Key; stash a client label on request.state for logging."""
    settings = get_settings()
    if not api_key or api_key not in settings.api_key_set:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "message": "Missing or invalid X-API-Key.",
            },
        )
    request.state.api_client = _client_label(api_key)
    return api_key
