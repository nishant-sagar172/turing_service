"""Add calls.from_number and calls.workflow_code for single calls.

Batch calls read both from their batch; single calls have no batch to hold them.

Revision ID: 0012_single_call_columns
Revises: 0011_drop_outcome_mirror
Create Date: 2026-09-16

"""

import sqlalchemy as sa
from alembic import op

revision = "0012_single_call_columns"
down_revision = "0011_drop_outcome_mirror"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calls", sa.Column("from_number", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "calls", sa.Column("workflow_code", sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("calls", "workflow_code")
    op.drop_column("calls", "from_number")
