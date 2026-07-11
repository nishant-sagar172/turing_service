"""Bolna-facing endpoints. Starts with a connectivity/credential status probe."""

from fastapi import APIRouter, Depends

from app.core.bolna_client import BolnaClient, BolnaError
from app.dependencies import get_bolna_client
from app.schemas.common import BolnaStatusResponse

router = APIRouter(prefix="/bolna", tags=["bolna"])


@router.get("/status", response_model=BolnaStatusResponse)
async def bolna_status(
    client: BolnaClient = Depends(get_bolna_client),
) -> BolnaStatusResponse:
    """Probe Bolna: validates the API key and confirms the API is reachable.

    Always returns HTTP 200 with a body describing the outcome, so callers can
    treat this as a dependency health check without handling exceptions.
    """
    try:
        account = await client.get_user()
        return BolnaStatusResponse(
            bolna="ok",
            base_url=client.base_url,
            account=account if isinstance(account, dict) else {"data": account},
        )
    except BolnaError as exc:
        return BolnaStatusResponse(
            bolna="error",
            base_url=client.base_url,
            detail=str(exc)
            + (f" | body={exc.payload}" if exc.payload is not None else ""),
        )
