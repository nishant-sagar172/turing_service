"""Request/response schemas for the /calls endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_scheduled_at(value: str | None) -> str | None:
    """Bolna rejects the ``Z`` UTC suffix (returns 500); convert to ``+00:00``."""
    if value is None:
        return None
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return value


class RetryConfig(BaseModel):
    """Auto-retry configuration for failed calls (passed through to Bolna)."""

    enabled: bool | None = None
    max_retries: int | None = None
    retry_on_statuses: list[str] | None = None
    retry_on_voicemail: bool | None = None
    retry_intervals_minutes: list[int] | None = None


class MakeCallRequest(BaseModel):
    """Trigger a single outbound call. Omit ``scheduled_at`` to call now."""

    agent_id: str = Field(description="Bolna agent id that will place the call.")
    recipient_phone_number: str = Field(
        description="Recipient number in E.164 format, e.g. +919876543210.",
    )
    from_phone_number: str | None = Field(
        default=None,
        description="Caller ID in E.164; defaults to the account's number.",
    )
    user_data: dict[str, Any] | None = Field(
        default=None,
        description="Dynamic variables injected into the agent prompt.",
    )
    scheduled_at: str | None = Field(
        default=None,
        description="ISO 8601 with numeric offset (e.g. 2026-07-10T18:30:00+00:00). "
        "If set, the call runs at that time instead of immediately.",
    )
    retry_config: RetryConfig | None = None
    bypass_call_guardrails: bool | None = Field(
        default=None,
        description="Skip Bolna's calling-time guardrail checks.",
    )

    @field_validator("scheduled_at")
    @classmethod
    def _normalize_scheduled_at(cls, value: str | None) -> str | None:
        return normalize_scheduled_at(value)

    def to_bolna_payload(self) -> dict[str, Any]:
        """Build the Bolna ``POST /call`` body, dropping unset fields."""
        return self.model_dump(exclude_none=True)


class MakeCallResponse(BaseModel):
    """Bolna's response to ``POST /call``, plus any turing validation warnings."""

    message: str | None = None
    status: str | None = Field(default=None, description="e.g. 'queued'.")
    execution_id: str | None = Field(
        default=None, description="Track the call via GET /calls/{execution_id}.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking notes, e.g. variables sent that the agent "
        "does not use.",
    )


class StopCallResponse(BaseModel):
    message: str | None = None
    status: str | None = None
    execution_id: str | None = None


class ExecutionResponse(BaseModel):
    """Call execution details from Bolna. Extra fields are preserved."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    agent_id: str | None = None
    status: str | None = None
    conversation_duration: float | None = None
    total_cost: float | None = None
    transcript: str | None = None
    extracted_data: dict[str, Any] | None = None
    telephony_data: dict[str, Any] | None = None
    error_message: str | None = None
