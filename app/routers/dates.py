"""Date resolver for voice agents: calendar arithmetic plus bookability."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.schemas.dates import DateResolveRequest, DateResolveResponse
from app.services.date_resolver import COUNTRY_RULES, resolve_date as resolve

router = APIRouter(prefix="/dates", tags=["dates"])


@router.post("/resolve", response_model=DateResolveResponse)
async def resolve_date(body: DateResolveRequest) -> DateResolveResponse:
    """Resolve a structured date phrase and say whether it is bookable."""
    rule = COUNTRY_RULES.get(body.country)
    if rule is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_country",
                "message": f"Country {body.country!r} is not supported.",
                "supported": sorted(COUNTRY_RULES),
            },
        )
    return resolve(body, datetime.now(UTC), rule)
