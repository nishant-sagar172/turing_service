"""turing's own persistence: clients (tenants), agent catalog, batches, calls,
request logs.

turing is the source of truth for full call records (transcripts, raw payloads,
cost). Every domain row is scoped to a ``client_id`` (tenant); the voice engine
(currently Bolna) is referenced by its own ids, stored as ``voice_*`` columns.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
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


class Client(TimestampMixin, Base):
    """A tenant: one registered consumer of this service."""

    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(128))

    api_keys: Mapped[list[ClientApiKey]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    config: Mapped[ClientConfig | None] = relationship(
        back_populates="client", cascade="all, delete-orphan", uselist=False
    )
    agent_configs: Mapped[list[ClientAgentConfig]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    phone_numbers: Mapped[list[ClientPhoneNumber]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )


class ClientApiKey(TimestampMixin, Base):
    """A hashed API key credential belonging to a client. Plaintext shown once."""

    __tablename__ = "client_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client: Mapped[Client] = relationship(back_populates="api_keys")


class ClientConfig(TimestampMixin, Base):
    """Per-client configuration: visibility, default caller ID, outcome webhook,
    and optional per-client LLM analysis overrides."""

    __tablename__ = "client_config"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    visible_fields: Mapped[dict | None] = mapped_column(JSONB)
    default_from_number: Mapped[str | None] = mapped_column(String(32))
    webhook_url: Mapped[str | None] = mapped_column(Text)
    webhook_secret: Mapped[str | None] = mapped_column(String(128))
    settings: Mapped[dict | None] = mapped_column(JSONB)

    # LLM analysis overrides — null means fall back to system env vars
    analysis_llm_provider: Mapped[str | None] = mapped_column(String(32))
    analysis_llm_model: Mapped[str | None] = mapped_column(String(128))
    analysis_prompt_hint: Mapped[str | None] = mapped_column(Text)
    analysis_llm_api_key_enc: Mapped[str | None] = mapped_column(Text)

    client: Mapped[Client] = relationship(back_populates="config")


class AgentCatalog(TimestampMixin, Base):
    """turing's cached view of an agent on the voice engine."""

    __tablename__ = "agent_catalog"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    voice_agent_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    agent_name: Mapped[str | None] = mapped_column(String(256))
    agent_status: Mapped[str | None] = mapped_column(String(32))
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_present: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClientAgentConfig(TimestampMixin, Base):
    """Per-client enablement + overrides for a catalog agent."""

    __tablename__ = "client_agent_config"
    __table_args__ = (
        UniqueConstraint("client_id", "voice_agent_id", name="uq_client_agent"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    voice_agent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(256))
    variable_overrides: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    client: Mapped[Client] = relationship(back_populates="agent_configs")


class PhoneNumberCatalog(TimestampMixin, Base):
    """Turing's cached view of phone numbers on the voice engine account."""

    __tablename__ = "phone_number_catalog"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    telephony_provider: Mapped[str | None] = mapped_column(String(64))
    rented: Mapped[bool | None] = mapped_column(Boolean)
    renewal_at: Mapped[str | None] = mapped_column(String(64))
    is_present: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client_assignments: Mapped[list[ClientPhoneNumber]] = relationship(
        back_populates="phone_number_catalog", cascade="all, delete-orphan"
    )


class ClientPhoneNumber(TimestampMixin, Base):
    """Assignment of a catalog phone number to a client (tenant)."""

    __tablename__ = "client_phone_numbers"
    __table_args__ = (
        UniqueConstraint("client_id", "phone_number_id", name="uq_client_phone_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    phone_number_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("phone_number_catalog.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    client: Mapped[Client] = relationship(back_populates="phone_numbers")
    phone_number_catalog: Mapped[PhoneNumberCatalog] = relationship(
        back_populates="client_assignments"
    )


class AgentDriftEvent(TimestampMixin, Base):
    """A durable record of a configured agent becoming unavailable upstream."""

    __tablename__ = "agent_drift_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True,
    )
    voice_agent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Batch(TimestampMixin, Base):
    """A campaign submitted by a client (maps 1:1 to a voice-engine batch)."""

    __tablename__ = "batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True,
    )
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    from_number: Mapped[str | None] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(16), default="batch", nullable=False)
    retry_config: Mapped[dict | None] = mapped_column(JSONB)
    voice_batch_id: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(128), default="created", nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_count: Mapped[int | None] = mapped_column(Integer)
    scheduled_at: Mapped[str | None] = mapped_column(String(64))
    recipients_snapshot: Mapped[list[Any] | None] = mapped_column(JSONB)

    calls: Mapped[list[Call]] = relationship(back_populates="batch")

    __table_args__ = (
        UniqueConstraint("client_id", "voice_batch_id", name="uq_batch_client_voice_id"),
    )


class Call(TimestampMixin, Base):
    """One outbound call (a voice-engine execution) — single sends and batch members."""

    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True,
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("batches.id"), index=True
    )
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    contact_number: Mapped[str | None] = mapped_column(String(32), index=True)
    patient_ref: Mapped[str | None] = mapped_column(String(128), index=True)
    voice_call_id: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text)
    recording_url: Mapped[str | None] = mapped_column(Text)
    extracted_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cost: Mapped[float | None] = mapped_column(Float)
    # Integer minor units, written alongside `cost` so aggregates can migrate off
    # binary-float money (which accumulates rounding error across large sums on
    # billing-adjacent figures). `cost` stays authoritative until readers move.
    cost_cents: Mapped[int | None] = mapped_column(Integer)
    duration: Mapped[float | None] = mapped_column(Float)
    hangup_reason: Mapped[str | None] = mapped_column(String(128))
    retry_count: Mapped[int | None] = mapped_column(Integer)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)

    batch: Mapped[Batch | None] = relationship(back_populates="calls")
    analysis: Mapped[CallAnalysis | None] = relationship(
        back_populates="call", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("client_id", "voice_call_id", name="uq_call_client_voice_id"),
        # Serves the tenant + date-range predicate every analytics query applies,
        # and the date_trunc grouping in the timeseries endpoint.
        Index("ix_calls_client_created", "client_id", "created_at"),
    )


class CallAnalysis(TimestampMixin, Base):
    """LLM-generated outcome classification for a completed call."""

    __tablename__ = "call_analysis"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("batches.id", ondelete="SET NULL"), index=True
    )
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    requests: Mapped[list[str] | None] = mapped_column(JSONB)
    urgency: Mapped[str | None] = mapped_column(String(16), index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    symptoms_reported: Mapped[list[str] | None] = mapped_column(JSONB)
    model_used: Mapped[str | None] = mapped_column(String(128))
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_llm_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    call: Mapped[Call] = relationship(back_populates="analysis")


class RequestLog(TimestampMixin, Base):
    """Audit log of every business API request handled by turing."""

    __tablename__ = "request_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), index=True,
    )
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(256), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
