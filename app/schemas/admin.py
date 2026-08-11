from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator


class CreateClientRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    contact_email: str | None = None
    status: str = Field(default="pending", pattern=r"^(pending|active)$")


class UpdateClientRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    contact_email: str | None = None

    @field_validator("contact_email", mode="before")
    @classmethod
    def allow_empty_email(cls, v: object) -> object:
        # empty string clears the field
        return None if v == "" else v


class ClientSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    contact_email: str | None
    status: str
    created_at: datetime
    approved_at: datetime | None


class ApproveResponse(BaseModel):
    client_id: uuid.UUID
    status: str
    api_key: str
    claim_url: str | None = None


class KeySummary(BaseModel):
    id: uuid.UUID
    key_prefix: str
    label: str | None
    status: str
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime


class IssueKeyRequest(BaseModel):
    label: str | None = None


class IssueKeyResponse(BaseModel):
    key_id: uuid.UUID
    api_key: str


class ClientConfigUpdate(BaseModel):
    default_from_number: str | None = None
    webhook_url: str | None = None
    webhook_secret: str | None = None
    visible_fields: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    # LLM analysis overrides — pass null to clear, omit to leave unchanged
    analysis_llm_provider: str | None = None
    analysis_llm_model: str | None = None
    analysis_prompt_hint: str | None = None
    # Write-only: stored encrypted, never returned in responses
    analysis_llm_api_key: str | None = None


class ClientConfigResponse(BaseModel):
    default_from_number: str | None
    webhook_url: str | None
    webhook_secret_set: bool
    visible_fields: dict[str, Any] | None
    settings: dict[str, Any] | None
    analysis_llm_provider: str | None
    analysis_llm_model: str | None
    analysis_prompt_hint: str | None
    analysis_llm_api_key_set: bool


class SetAgentsRequest(BaseModel):
    voice_agent_ids: list[str]


class SyncResponse(BaseModel):
    synced: int
    removed: int
    drift_events: int


class CatalogAgentSummary(BaseModel):
    voice_agent_id: str
    agent_name: str | None
    agent_status: str | None
    is_present: bool
    last_synced_at: datetime | None


class ClientAgentSummary(BaseModel):
    voice_agent_id: str
    enabled: bool
    display_name: str | None
    variable_overrides: dict[str, Any] | None
    agent_name: str | None
    is_present: bool | None


class AgentConfigUpdate(BaseModel):
    display_name: str | None = None
    variable_overrides: dict[str, Any] | None = None


class BatchSummaryAdmin(BaseModel):
    id: uuid.UUID
    voice_batch_id: str | None
    agent_id: str
    status: str
    total_count: int
    scheduled_at: str | None
    created_at: datetime


class PhoneNumberCatalogSummary(BaseModel):
    id: uuid.UUID
    phone_number: str
    telephony_provider: str | None
    rented: bool | None
    renewal_at: str | None
    is_present: bool
    last_synced_at: datetime | None


class ClientPhoneNumberSummary(BaseModel):
    id: uuid.UUID
    phone_number: str
    telephony_provider: str | None
    rented: bool | None
    is_present: bool


class SetPhoneNumbersRequest(BaseModel):
    phone_number_ids: list[uuid.UUID]


class PhoneNumberSyncResponse(BaseModel):
    synced: int
    removed: int
