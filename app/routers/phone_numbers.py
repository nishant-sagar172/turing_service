"""/phone-numbers endpoint — lists available caller IDs for the frontend dropdown."""

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.core.bolna_client import BolnaClient
from app.dependencies import get_bolna_client
from app.schemas.phone_numbers import PhoneNumber, PhoneNumbersResponse

router = APIRouter(prefix="/phone-numbers", tags=["phone-numbers"])


@router.get("", response_model=PhoneNumbersResponse)
async def list_phone_numbers(
    client: BolnaClient = Depends(get_bolna_client),
    settings: Settings = Depends(get_settings),
) -> PhoneNumbersResponse:
    """List the account's owned numbers and the service's configured default.

    Frontends populate the caller-ID dropdown from ``phone_numbers`` and
    pre-select ``default_from_number``.
    """
    result = await client.list_phone_numbers()
    numbers = [PhoneNumber.model_validate(item) for item in result]
    return PhoneNumbersResponse(
        default_from_number=settings.bolna_default_from_number,
        phone_numbers=numbers,
    )
