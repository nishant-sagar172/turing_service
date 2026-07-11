"""Schemas for the /phone-numbers endpoint (caller-ID dropdown source)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PhoneNumber(BaseModel):
    """A phone number owned on the Bolna account. Extra fields are preserved."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    phone_number: str | None = None
    agent_id: str | None = None
    telephony_provider: str | None = None
    rented: bool | None = None
    price: str | None = None
    renewal_at: str | None = None


class PhoneNumbersResponse(BaseModel):
    """Available caller IDs plus which one the service uses by default."""

    default_from_number: str | None = None
    phone_numbers: list[PhoneNumber] = []
