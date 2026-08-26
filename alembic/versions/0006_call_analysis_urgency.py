"""Add urgency, confidence, symptoms_reported columns to call_analysis

Revision ID: 0006_call_analysis_urgency
Revises: 0005_call_analysis
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_call_analysis_urgency"
down_revision = "0005_call_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("call_analysis", sa.Column("urgency", sa.String(16), nullable=True))
    op.add_column("call_analysis", sa.Column("confidence", sa.Float, nullable=True))
    op.add_column("call_analysis", sa.Column("symptoms_reported", JSONB, nullable=True))
    op.create_index("ix_call_analysis_urgency", "call_analysis", ["urgency"])


def downgrade() -> None:
    op.drop_index("ix_call_analysis_urgency", table_name="call_analysis")
    op.drop_column("call_analysis", "symptoms_reported")
    op.drop_column("call_analysis", "confidence")
    op.drop_column("call_analysis", "urgency")
