from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext
from app.config import Settings, get_settings
from app.db.session import get_session
from app.dependencies import get_current_tenant
from app.schemas.phone_numbers import PhoneNumber, PhoneNumbersResponse
from app.services import phone_number_sync
from app.services.tenants import get_config

router = APIRouter(prefix="/phone-numbers", tags=["phone-numbers"])


@router.get("", response_model=PhoneNumbersResponse)
async def list_phone_numbers(
    tenant: TenantContext = Depends(get_current_tenant),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> PhoneNumbersResponse:
    assigned = await phone_number_sync.get_assigned_numbers(session, tenant.client_id)
    numbers = [PhoneNumber(phone_number=n) for n in assigned]

    config = await get_config(session, tenant.client_id)
    default_from_number = (
        config.default_from_number
        if config and config.default_from_number
        else settings.voice_default_from_number
    )
    return PhoneNumbersResponse(
        default_from_number=default_from_number,
        phone_numbers=numbers,
    )
