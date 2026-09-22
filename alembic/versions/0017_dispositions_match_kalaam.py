"""Clear sub_status values Kalaam has no child status for.

Revision ID: 0017_dispositions_match_kalaam
Revises: 0016_remap_dispositions
Create Date: 2026-09-20

"""

from alembic import op
from sqlalchemy import text

revision = "0017_dispositions_match_kalaam"
down_revision = "0016_remap_dispositions"
branch_labels = None
depends_on = None

_OUTCOMES = (
    "wants_second_opinion",
    "on_medications",
    "medical_clearance_pending",
    "waiting_referral_letter",
    "call_dropped",
)


def upgrade() -> None:
    bind = op.get_bind()
    for outcome in _OUTCOMES:
        bind.execute(
            text("UPDATE call_analysis SET sub_status = NULL WHERE call_outcome = :o"),
            {"o": outcome},
        )


def downgrade() -> None:
    pass
