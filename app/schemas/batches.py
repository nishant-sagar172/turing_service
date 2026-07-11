"""Request/response schemas for the /batches endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.calls import RetryConfig, normalize_scheduled_at

CONTACT_COLUMN = "contact_number"


class CreateBatchRequest(BaseModel):
    """Create a batch from a JSON list of recipients (converted to CSV for Bolna).

    Each recipient must include ``contact_number`` (E.164). Any other keys
    become dynamic prompt variables for that call.
    """

    agent_id: str = Field(description="Bolna agent id used for every call.")
    recipients: list[dict[str, Any]] = Field(
        description="List of recipients; each needs a 'contact_number' key.",
        min_length=1,
    )
    from_phone_numbers: list[str] | None = Field(
        default=None, description="Optional pool of caller IDs (E.164).",
    )
    retry_config: RetryConfig | None = None
    webhook_url: str | None = Field(
        default=None, description="Per-batch webhook for execution updates.",
    )

    @model_validator(mode="after")
    def _check_contact_numbers(self) -> CreateBatchRequest:
        for index, recipient in enumerate(self.recipients):
            if not str(recipient.get(CONTACT_COLUMN, "")).strip():
                raise ValueError(
                    f"recipient at index {index} is missing '{CONTACT_COLUMN}'"
                )
        return self


class CreateBatchResponse(BaseModel):
    batch_id: str | None = None
    state: str | None = Field(default=None, description="e.g. 'created'.")
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking notes, e.g. variables sent that the agent "
        "does not use.",
    )


class ScheduleBatchRequest(BaseModel):
    """Schedule a created batch. Time must be >= 2 min out; Bolna rounds up to
    the next 10-minute mark."""

    scheduled_at: str = Field(
        description="ISO 8601 with numeric offset, e.g. 2026-07-10T18:30:00+00:00.",
    )
    bypass_call_guardrails: bool | None = None

    @field_validator("scheduled_at")
    @classmethod
    def _normalize_scheduled_at(cls, value: str) -> str:
        return normalize_scheduled_at(value)

    def to_bolna_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ScheduleBatchResponse(BaseModel):
    message: str | None = None
    state: str | None = Field(default=None, description="e.g. 'scheduled'.")


class BatchActionResponse(BaseModel):
    """Response for stop/delete actions."""

    message: str | None = None
    state: str | None = None


class BatchSummary(BaseModel):
    """A batch record as returned by Bolna. Extra fields are preserved."""

    model_config = ConfigDict(extra="allow")

    batch_id: str | None = None
    status: str | None = None
    scheduled_at: str | None = None
    file_name: str | None = None
    valid_contacts: int | None = None
    total_contacts: int | None = None
    from_phone_numbers: list[str] | None = None
    execution_status: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None
