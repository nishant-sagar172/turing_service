"""One-time API-key claim endpoint.

Two-phase flow:
  GET  /v1/claim/{token}  — non-destructive peek (safe for URL unfurlers)
  POST /v1/claim/{token}  — atomic GETDEL; burns the link on success

Both paths are open (no X-API-Key / X-Admin-Key required) — registered in
``_OPEN_PREFIXES`` in middleware.py.  The token is validated by its presence
in Redis; expired or already-burned tokens return 404.  The two responses are
deliberately identical (both 404) to avoid an oracle that distinguishes
"never existed" from "already claimed".
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_redis
from app.schemas.claim import ClaimPeekResponse, ClaimResponse
from app.services import claim_links

router = APIRouter(prefix="/claim", tags=["claim"])


@router.get("/{token}", response_model=ClaimPeekResponse)
async def peek_claim(
    token: str,
    redis=Depends(get_redis),
) -> ClaimPeekResponse:
    if redis is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "claim_service_unavailable",
                "message": "Claim link service is not configured on this deployment.",
            },
        )
    result = await claim_links.peek(redis, token)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": "Claim link is invalid, expired, or already used.",
            },
        )
    return ClaimPeekResponse(
        client_name=result.client_name,
        expires_in_seconds=result.expires_in_seconds,
    )


@router.post("/{token}", response_model=ClaimResponse)
async def burn_claim(
    token: str,
    redis=Depends(get_redis),
) -> ClaimResponse:
    if redis is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "claim_service_unavailable",
                "message": "Claim link service is not configured on this deployment.",
            },
        )
    result = await claim_links.burn(redis, token)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": "Claim link is invalid, expired, or already used.",
            },
        )
    client_name, api_key = result
    return ClaimResponse(client_name=client_name, api_key=api_key)
