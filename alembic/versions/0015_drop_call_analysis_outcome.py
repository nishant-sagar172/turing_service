"""Drop call_analysis.outcome — replaced by call_outcome + disposition_status.

Nothing reads it: the ORM model and every consumer moved to call_outcome /
disposition_status / sub_status. Pre-0009 rows have NULL call_outcome and stay
unclassified (analytics excludes NULL). Downgrade restores the column and index
but not the old values.

Revision ID: 0015_drop_call_analysis_outcome
Revises: 0014_call_client_ref
Create Date: 2026-09-19

"""

import sqlalchemy as sa
from alembic import op

revision = "0015_drop_call_analysis_outcome"
down_revision = "0014_call_client_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF EXISTS so the drop is a no-op where outcome was already removed; the
    # dependent index drops with the column.
    op.execute("ALTER TABLE call_analysis DROP COLUMN IF EXISTS outcome")


def downgrade() -> None:
    # NOT NULL needs a value for existing rows; call_outcome is what the column
    # mirrored, and "other" stands in where that is NULL.
    op.add_column(
        "call_analysis", sa.Column("outcome", sa.String(length=32), nullable=True)
    )
    op.execute("UPDATE call_analysis SET outcome = COALESCE(call_outcome, 'other')")
    op.alter_column("call_analysis", "outcome", nullable=False)
    op.create_index("ix_call_analysis_outcome", "call_analysis", ["outcome"])
