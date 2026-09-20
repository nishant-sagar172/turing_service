"""Re-map call_analysis dispositions to the client Call-Outcome guide.

The disposition_status / sub_status values were coarse buckets (Converted,
Follow Up, ...). Clients read these, so they must match the agreed guide
exactly (Visited, Booking, Cost Help, Insurance Loan Pending, ...). The mapping
is deterministic from the stored workflow_code + call_outcome, so existing rows
are re-mapped in place; only rows with a call_outcome are touched (pre-rollout
rows stay NULL/unclassified).

Not reversible in the data sense — downgrade is a no-op; the previous coarse
labels are not restored.

Revision ID: 0016_remap_dispositions
Revises: 0015_drop_call_analysis_outcome
Create Date: 2026-09-20

"""

from alembic import op
from sqlalchemy import text

revision = "0016_remap_dispositions"
down_revision = "0015_drop_call_analysis_outcome"
branch_labels = None
depends_on = None

# call_outcome -> (disposition_status, sub_status), for every workflow.
_COMMON = [
    ("completed_visited", "Visited", None),
    ("scheduled_booking", "Booking", None),
    ("declined", "Declined", "Other"),
    ("wants_cost_estimate", "Cost Help", "Waiting Estimate"),
    ("wants_discount", "Cost Help", "Discount Asked"),
    ("wants_second_opinion", "Wants Second Opinion", "Wants Second Opinion"),
    ("waiting_doctor_confirmation", "Waiting For Doctor Reports", "Doctor OK Pending"),
    ("waiting_reports", "Waiting For Doctor Reports", "Report Pending"),
    (
        "waiting_referral_letter",
        "Waiting for Referral Letter",
        "Waiting for Referral Letter",
    ),
    ("insurance_concern", "Insurance Loan Pending", "Insurance Approval Pending"),
    ("loan_required", "Insurance Loan Pending", "Loan Approval Pending"),
    ("on_medications", "On Medications", "On Medications"),
    (
        "medical_clearance_pending",
        "Medical clearance pending",
        "Medical clearance pending",
    ),
    ("follow_up", "Follow Up", None),
    ("call_dropped", "Follow Up", "Call Dropped"),
    ("not_connected", "Couldn't reach", "Busy"),
    ("escalation", "Escalation", None),
    ("no_output", "No Output", None),
]


def upgrade() -> None:
    bind = op.get_bind()
    stmt = text(
        "UPDATE call_analysis SET disposition_status = :status, "
        "sub_status = :sub WHERE call_outcome = :outcome"
    )
    for outcome, status, sub in _COMMON:
        bind.execute(stmt, {"outcome": outcome, "status": status, "sub": sub})

    # done_elsewhere is Not Interested in every workflow, but the sub_status
    # wording differs: IPD admitted elsewhere vs done elsewhere.
    bind.execute(
        text(
            "UPDATE call_analysis SET disposition_status = 'Not Interested', "
            "sub_status = 'Admitted Elsewhere' "
            "WHERE call_outcome = 'done_elsewhere' AND workflow_code = 'ipd'"
        )
    )
    bind.execute(
        text(
            "UPDATE call_analysis SET disposition_status = 'Not Interested', "
            "sub_status = 'Done Elsewhere' "
            "WHERE call_outcome = 'done_elsewhere' "
            "AND (workflow_code IS DISTINCT FROM 'ipd')"
        )
    )


def downgrade() -> None:
    # Data-only backfill; the previous coarse labels are not restored.
    pass
