"""Add calls.notified_at — the exactly-once client-notification claim.

NULL means the call still owes its client a terminal-outcome notification.
``complete_call`` claims a row by setting this with a conditional UPDATE, and the
recovery pass re-picks any terminal row still NULL after a crash or failed
delivery.

Existing terminal rows are backfilled to their last-updated time so the recovery
pass treats already-handled history as done and does not re-send it. Non-terminal
rows stay NULL so they can be claimed when they finish.

Revision ID: 0013_call_notified_at
Revises: 0012_single_call_columns
Create Date: 2026-09-18

"""

import sqlalchemy as sa
from alembic import op

from app.core.call_status import TERMINAL_STATUSES

revision = "0013_call_notified_at"
down_revision = "0012_single_call_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calls",
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_calls_notified_at", "calls", ["notified_at"])

    terminal = ", ".join(f"'{status}'" for status in sorted(TERMINAL_STATUSES))
    op.execute(
        "UPDATE calls SET notified_at = COALESCE(updated_at, created_at) "
        f"WHERE status IN ({terminal}) AND notified_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_calls_notified_at", table_name="calls")
    op.drop_column("calls", "notified_at")
