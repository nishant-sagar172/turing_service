"""Create call_analysis table for LLM-generated call outcome classification

Revision ID: 0005_call_analysis
Revises: 0004_client_config_llm_columns
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0005_call_analysis"
down_revision = "0004_client_config_llm_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "call_analysis",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("call_id", UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("batch_id", UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("requests", JSONB, nullable=True),
        sa.Column("model_used", sa.String(128), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_llm_response", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("call_id", name="uq_call_analysis_call_id"),
    )
    op.create_index("ix_call_analysis_call_id", "call_analysis", ["call_id"])
    op.create_index("ix_call_analysis_client_id", "call_analysis", ["client_id"])
    op.create_index("ix_call_analysis_agent_id", "call_analysis", ["agent_id"])
    op.create_index("ix_call_analysis_batch_id", "call_analysis", ["batch_id"])
    op.create_index("ix_call_analysis_outcome", "call_analysis", ["outcome"])


def downgrade() -> None:
    op.drop_table("call_analysis")
