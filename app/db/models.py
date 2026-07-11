"""turing's own persistence: batches, calls (executions), request logs.

turing is the source of truth for full call records (transcripts, raw payloads,
cost); consumers such as Kalaam store only a lean outcome + a reference here.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Batch(TimestampMixin, Base):
    """A campaign submitted by a consumer (maps 1:1 to a Bolna batch)."""

    __tablename__ = "batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client: Mapped[str | None] = mapped_column(String(64))
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    from_number: Mapped[str | None] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(16), default="batch", nullable=False)
    retry_config: Mapped[dict | None] = mapped_column(JSONB)
    bolna_batch_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_count: Mapped[int | None] = mapped_column(Integer)
    scheduled_at: Mapped[str | None] = mapped_column(String(64))
    recipients_snapshot: Mapped[list | None] = mapped_column(JSONB)

    calls: Mapped[list[Call]] = relationship(back_populates="batch")


class Call(TimestampMixin, Base):
    """One outbound call (a Bolna execution) — single sends and batch members."""

    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("batches.id"), index=True
    )
    client: Mapped[str | None] = mapped_column(String(64))
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    contact_number: Mapped[str | None] = mapped_column(String(32), index=True)
    patient_ref: Mapped[str | None] = mapped_column(String(128), index=True)
    bolna_execution_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text)
    recording_url: Mapped[str | None] = mapped_column(Text)
    extracted_data: Mapped[dict | None] = mapped_column(JSONB)
    cost: Mapped[float | None] = mapped_column(Float)
    duration: Mapped[float | None] = mapped_column(Float)
    hangup_reason: Mapped[str | None] = mapped_column(String(128))
    retry_count: Mapped[int | None] = mapped_column(Integer)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)

    batch: Mapped[Batch | None] = relationship(back_populates="calls")


class RequestLog(TimestampMixin, Base):
    """Audit log of every business API request handled by turing."""

    __tablename__ = "request_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    client: Mapped[str | None] = mapped_column(String(64))
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(256), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
