"""Re-map call_analysis dispositions to the exact Kalaam status strings.

Revision ID: 0019_kalaam_dispositions
Revises: 0018_batch_notified_at
Create Date: 2026-09-27

"""

from alembic import op
from sqlalchemy import text

revision = "0019_kalaam_dispositions"
down_revision = "0018_batch_notified_at"
branch_labels = None
depends_on = None

# call_outcome -> ((old status, old sub_status), (new status, new sub_status))
_CHANGES: list[tuple[str, tuple[str, str | None], tuple[str, str | None]]] = [
    ("declined", ("Declined", "Other"), ("Not Interested", "Other")),
    (
        "wants_cost_estimate",
        ("Cost Help", "Waiting Estimate"),
        ("Cost Help", "Waiting estimate"),
    ),
    (
        "wants_discount",
        ("Cost Help", "Discount Asked"),
        ("Cost Help", "Discount asked"),
    ),
    (
        "wants_second_opinion",
        ("Wants Second Opinion", None),
        ("Wants second opinion", None),
    ),
    (
        "waiting_doctor_confirmation",
        ("Waiting For Doctor Reports", "Doctor OK Pending"),
        ("Waiting for doctor / reports", "Doctor OK pending"),
    ),
    (
        "waiting_reports",
        ("Waiting For Doctor Reports", "Report Pending"),
        ("Waiting for doctor / reports", "Report pending"),
    ),
    (
        "insurance_concern",
        ("Insurance Loan Pending", "Insurance Approval Pending"),
        ("Insurance / Loan pending", "Insurance approval pending"),
    ),
    (
        "loan_required",
        ("Insurance Loan Pending", "Loan Approval Pending"),
        ("Insurance / Loan pending", "Loan approval pending"),
    ),
    (
        "medical_clearance_pending",
        ("Medical clearance pending", None),
        ("Medical Clearance Pending", None),
    ),
    ("not_connected", ("Couldn't reach", "Busy"), ("Couldn't Reach", "Busy")),
]


def _apply(use_new: bool) -> None:
    for outcome, old, new in _CHANGES:
        status, sub_status = new if use_new else old
        op.execute(
            text(
                "UPDATE call_analysis SET disposition_status = :status, "
                "sub_status = :sub_status WHERE call_outcome = :outcome"
            ).bindparams(status=status, sub_status=sub_status, outcome=outcome)
        )


def upgrade() -> None:
    _apply(use_new=True)


def downgrade() -> None:
    _apply(use_new=False)
