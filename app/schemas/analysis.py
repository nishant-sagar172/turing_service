"""Schemas for call analysis (LLM classification) and enriched call responses."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.db.models import CallAnalysis


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

    @classmethod
    def from_model(cls, analysis: "CallAnalysis | None") -> "CallAnalysisResult | None":
        if analysis is None:
            return None
        return cls(
            outcome=analysis.outcome,
            summary=analysis.summary,
            reason=analysis.reason,
            requests=analysis.requests or [],
            urgency=analysis.urgency,
            confidence=analysis.confidence,
            symptoms_reported=analysis.symptoms_reported or [],
            model_used=analysis.model_used,
            analyzed_at=analysis.analyzed_at,
        )


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
