"""Add batches.notified_at — the exactly-once client-notification claim.

Mirrors 0013_call_notified_at for the batch-status webhook, which today has
no retry path: a missed or failed delivery to the client is gone for good.

Revision ID: 0018_batch_notified_at
Revises: 0017_dispositions_match_kalaam
Create Date: 2026-09-22

"""

import sqlalchemy as sa
from alembic import op

revision = "0018_batch_notified_at"
down_revision = "0017_dispositions_match_kalaam"
branch_labels = None
depends_on = None

_TERMINAL = ("completed", "stopped", "failed", "cancelled", "canceled")


def upgrade() -> None:
    op.add_column(
        "batches",
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial: only the (normally tiny) unnotified subset ever needs scanning.
    op.create_index(
        "ix_batches_notified_at",
        "batches",
        ["notified_at"],
        postgresql_where=sa.text("notified_at IS NULL"),
    )

    terminal = ", ".join(f"'{status}'" for status in _TERMINAL)
    op.execute(
        "UPDATE batches SET notified_at = COALESCE(updated_at, created_at) "
        f"WHERE status IN ({terminal}) AND notified_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_batches_notified_at", table_name="batches")
    op.drop_column("batches", "notified_at")
