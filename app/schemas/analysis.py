"""Schemas for call analysis (LLM classification) and enriched call responses."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CallAnalysisResult(BaseModel):
    outcome: str
    summary: str | None
    reason: str | None
    requests: list[str]
    urgency: str | None = None
    confidence: float | None = None
    symptoms_reported: list[str] | None = None
    model_used: str | None
    analyzed_at: datetime | None


class CallListItem(BaseModel):
    call_id: str | None
    agent_id: str
    batch_id: uuid.UUID | None
    contact_number: str | None
    from_number: str | None
    status: str
    duration: float | None
    cost: float | None
    hangup_reason: str | None
    recording_url: str | None
    created_at: str | None
    analysis: CallAnalysisResult | None


class CallDetail(CallListItem):
    transcript: str | None
    extracted_data: dict[str, Any] | None
    patient_ref: str | None
    retry_count: int | None


class CallListResponse(BaseModel):
    items: list[CallListItem]
    total: int
    page: int
    page_size: int
    pages: int
