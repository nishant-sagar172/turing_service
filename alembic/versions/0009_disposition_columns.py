"""Add disposition columns to call_analysis, task_type to batches and client_config

call_analysis gains: call_outcome, disposition_status, sub_status, task_type
batches gains: task_type
client_config gains: default_task_type

All nullable — existing rows unaffected, no data backfill.

Revision ID: 0009_disposition_columns
Revises: 0008_calls_cost_cents
Create Date: 2026-09-15

"""

from alembic import op
import sqlalchemy as sa

revision = "0009_disposition_columns"
down_revision = "0008_calls_cost_cents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "call_analysis",
        sa.Column("call_outcome", sa.String(64), nullable=True),
    )
    op.add_column(
        "call_analysis",
        sa.Column("disposition_status", sa.String(64), nullable=True),
    )
    op.add_column(
        "call_analysis",
        sa.Column("sub_status", sa.String(64), nullable=True),
    )
    op.add_column(
        "call_analysis",
        sa.Column("task_type", sa.String(32), nullable=True),
    )
    op.create_index("ix_call_analysis_call_outcome", "call_analysis", ["call_outcome"])
    op.create_index(
        "ix_call_analysis_disposition_status", "call_analysis", ["disposition_status"]
    )
    op.create_index("ix_call_analysis_task_type", "call_analysis", ["task_type"])

    op.add_column(
        "batches",
        sa.Column("task_type", sa.String(32), nullable=True),
    )

    op.add_column(
        "client_config",
        sa.Column("default_task_type", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("client_config", "default_task_type")
    op.drop_column("batches", "task_type")

    op.drop_index("ix_call_analysis_task_type", table_name="call_analysis")
    op.drop_index("ix_call_analysis_disposition_status", table_name="call_analysis")
    op.drop_index("ix_call_analysis_call_outcome", table_name="call_analysis")
    op.drop_column("call_analysis", "task_type")
    op.drop_column("call_analysis", "sub_status")
    op.drop_column("call_analysis", "disposition_status")
    op.drop_column("call_analysis", "call_outcome")
