"""initial schema: batches, calls, request_logs

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "batches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client", sa.String(64), nullable=True),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("from_number", sa.String(32), nullable=True),
        sa.Column("mode", sa.String(16), nullable=False, server_default="batch"),
        sa.Column("retry_config", JSONB, nullable=True),
        sa.Column("bolna_batch_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("total_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("valid_count", sa.Integer, nullable=True),
        sa.Column("scheduled_at", sa.String(64), nullable=True),
        sa.Column("recipients_snapshot", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_batches_bolna_batch_id", "batches",
                    ["bolna_batch_id"], unique=True)

    op.create_table(
        "calls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", UUID(as_uuid=True),
                  sa.ForeignKey("batches.id"), nullable=True),
        sa.Column("client", sa.String(64), nullable=True),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("contact_number", sa.String(32), nullable=True),
        sa.Column("patient_ref", sa.String(128), nullable=True),
        sa.Column("bolna_execution_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("transcript", sa.Text, nullable=True),
        sa.Column("recording_url", sa.Text, nullable=True),
        sa.Column("extracted_data", JSONB, nullable=True),
        sa.Column("cost", sa.Float, nullable=True),
        sa.Column("duration", sa.Float, nullable=True),
        sa.Column("hangup_reason", sa.String(128), nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=True),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_calls_batch_id", "calls", ["batch_id"])
    op.create_index("ix_calls_contact_number", "calls", ["contact_number"])
    op.create_index("ix_calls_patient_ref", "calls", ["patient_ref"])
    op.create_index("ix_calls_bolna_execution_id", "calls",
                    ["bolna_execution_id"], unique=True)

    op.create_table(
        "request_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("client", sa.String(64), nullable=True),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("endpoint", sa.String(256), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("latency_ms", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_request_logs_request_id", "request_logs", ["request_id"])


def downgrade() -> None:
    op.drop_table("request_logs")
    op.drop_table("calls")
    op.drop_table("batches")
