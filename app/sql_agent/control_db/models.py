"""SQL Builder Agent control-plane models (spec §2) — dedicated sql_agent_db.

Own DeclarativeBase, deliberately NOT ``app.db.models.Base``: these tables
live in a separate database and must never end up in turing's Alembic chain
or turing_db. Schema is applied via ``control_db.bootstrap`` (plain
``create_all``), not Alembic, while the schema is still moving fast.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Vector column width is baked into the DDL at create-time, so it lives here
# as a constant; the bootstrap refuses to run if SqlAgentSettings disagrees
# (changing dimension requires re-embedding everything, not a silent config flip).
EMBEDDING_DIM = 1536


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


class Workspace(TimestampMixin, Base):
    """A target-database onboarding unit: one schema/glossary/example corpus."""

    __tablename__ = "sql_agent_workspaces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    row_scoping_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    datasources: Mapped[list[Datasource]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    tables: Mapped[list[TableMeta]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class Datasource(TimestampMixin, Base):
    """Connection metadata for a workspace's target DB (1:1 for v1).

    Holds the NAME of the env var containing the read-only connection string —
    never the credential itself.
    """

    __tablename__ = "sql_agent_datasources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sql_agent_workspaces.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    dialect: Mapped[str] = mapped_column(String(32), default="postgres", nullable=False)
    connection_env_var: Mapped[str] = mapped_column(String(128), nullable=False)
    read_only_role_name: Mapped[str | None] = mapped_column(String(128))
    statement_timeout_ms: Mapped[int] = mapped_column(
        Integer, default=10000, nullable=False
    )
    default_row_limit: Mapped[int] = mapped_column(Integer, default=200, nullable=False)

    workspace: Mapped[Workspace] = relationship(back_populates="datasources")


class TableMeta(TimestampMixin, Base):
    """One introspected table of a workspace's target DB, plus its embedding."""

    __tablename__ = "sql_agent_tables"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "schema_name",
            "table_name",
            name="uq_sql_agent_tables_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sql_agent_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    schema_name: Mapped[str] = mapped_column(String(128), nullable=False)
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    row_count_estimate: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_hash: Mapped[str | None] = mapped_column(String(64))
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    workspace: Mapped[Workspace] = relationship(back_populates="tables")
    columns: Mapped[list[ColumnMeta]] = relationship(
        back_populates="table", cascade="all, delete-orphan"
    )


class ColumnMeta(TimestampMixin, Base):
    """One column of an introspected table. No embedding — retrieval is table-level."""

    __tablename__ = "sql_agent_columns"
    __table_args__ = (
        UniqueConstraint(
            "table_id", "column_name", name="uq_sql_agent_columns_identity"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sql_agent_tables.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    column_name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_type: Mapped[str] = mapped_column(String(128), nullable=False)
    is_nullable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_primary_key: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_foreign_key: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sample_values: Mapped[list[Any] | None] = mapped_column(JSONB)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    table: Mapped[TableMeta] = relationship(back_populates="columns")


class Relationship(TimestampMixin, Base):
    """A join edge between two tables: auto-detected FK or manually declared."""

    __tablename__ = "sql_agent_relationships"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sql_agent_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sql_agent_tables.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_column: Mapped[str] = mapped_column(String(128), nullable=False)
    to_table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sql_agent_tables.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_column: Mapped[str] = mapped_column(String(128), nullable=False)
    relationship_type: Mapped[str] = mapped_column(
        String(16), default="fk_auto", nullable=False
    )
    join_hint: Mapped[str | None] = mapped_column(Text)


class GlossaryTerm(TimestampMixin, Base):
    """A business term definition, optionally mapped to a table/column."""

    __tablename__ = "sql_agent_glossary"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sql_agent_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    term: Mapped[str] = mapped_column(String(256), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    maps_to_table_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sql_agent_tables.id", ondelete="SET NULL")
    )
    maps_to_column_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sql_agent_columns.id", ondelete="SET NULL")
    )
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)


class Example(TimestampMixin, Base):
    """A curated/verified (question, SQL) pair — the few-shot example bank."""

    __tablename__ = "sql_agent_examples"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sql_agent_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    tables_used: Mapped[list[str] | None] = mapped_column(JSONB)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)


class QueryAudit(Base):
    """Full trace of one propose/execute run. Append-only; always written."""

    __tablename__ = "sql_agent_query_audit"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sql_agent_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    request_id: Mapped[str | None] = mapped_column(String(128), index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    enhanced_question: Mapped[str | None] = mapped_column(Text)
    selected_tables: Mapped[list[str] | None] = mapped_column(JSONB)
    generated_sql: Mapped[str | None] = mapped_column(Text)
    final_sql: Mapped[str | None] = mapped_column(Text)
    critic_notes: Mapped[list[Any] | None] = mapped_column(JSONB)
    validation_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    repair_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    row_count: Mapped[int | None] = mapped_column(Integer)
    execution_ms: Mapped[float | None] = mapped_column(Float)
    llm_tokens_used: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    model_versions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    repair_logs: Mapped[list[RepairLog]] = relationship(
        back_populates="query_audit", cascade="all, delete-orphan"
    )


class RepairLog(Base):
    """One repair attempt inside a run — what failed, why, and the fix tried."""

    __tablename__ = "sql_agent_repair_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query_audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sql_agent_query_audit.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    failed_sql: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    repaired_sql: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    query_audit: Mapped[QueryAudit] = relationship(back_populates="repair_logs")
