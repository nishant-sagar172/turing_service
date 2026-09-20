"""Deterministic disposition mapping: (workflow_code, call_outcome) → (status, sub_status).

Pure Python — no DB, no LLM, no I/O. The LLM classifies what happened on the
call; this module assigns the business label.
"""

from __future__ import annotations

from typing import NamedTuple

_ANY_WORKFLOW = "*"


class DispositionResult(NamedTuple):
    status: str
    sub_status: str | None


DISPOSITION_MAP: dict[tuple[str, str], DispositionResult] = {
    # Visited / Booking
    (_ANY_WORKFLOW, "completed_visited"): DispositionResult("Visited", None),
    (_ANY_WORKFLOW, "scheduled_booking"): DispositionResult("Booking", None),
    # Not Interested — IPD says "Admitted Elsewhere", every other workflow "Done
    # Elsewhere"; both are still Not Interested.
    ("ipd", "done_elsewhere"): DispositionResult(
        "Not Interested", "Admitted Elsewhere"
    ),
    (_ANY_WORKFLOW, "done_elsewhere"): DispositionResult(
        "Not Interested", "Done Elsewhere"
    ),
    (_ANY_WORKFLOW, "declined"): DispositionResult("Declined", "Other"),
    # Cost Help
    (_ANY_WORKFLOW, "wants_cost_estimate"): DispositionResult(
        "Cost Help", "Waiting Estimate"
    ),
    (_ANY_WORKFLOW, "wants_discount"): DispositionResult("Cost Help", "Discount Asked"),
    # Second opinion
    (_ANY_WORKFLOW, "wants_second_opinion"): DispositionResult(
        "Wants Second Opinion", "Wants Second Opinion"
    ),
    # Waiting For Doctor Reports
    (_ANY_WORKFLOW, "waiting_doctor_confirmation"): DispositionResult(
        "Waiting For Doctor Reports", "Doctor OK Pending"
    ),
    (_ANY_WORKFLOW, "waiting_reports"): DispositionResult(
        "Waiting For Doctor Reports", "Report Pending"
    ),
    (_ANY_WORKFLOW, "waiting_referral_letter"): DispositionResult(
        "Waiting for Referral Letter", "Waiting for Referral Letter"
    ),
    # IPD finance / clearance
    (_ANY_WORKFLOW, "insurance_concern"): DispositionResult(
        "Insurance Loan Pending", "Insurance Approval Pending"
    ),
    (_ANY_WORKFLOW, "loan_required"): DispositionResult(
        "Insurance Loan Pending", "Loan Approval Pending"
    ),
    (_ANY_WORKFLOW, "on_medications"): DispositionResult(
        "On Medications", "On Medications"
    ),
    (_ANY_WORKFLOW, "medical_clearance_pending"): DispositionResult(
        "Medical clearance pending", "Medical clearance pending"
    ),
    # Follow Up
    (_ANY_WORKFLOW, "follow_up"): DispositionResult("Follow Up", None),
    (_ANY_WORKFLOW, "call_dropped"): DispositionResult("Follow Up", "Call Dropped"),
    # Not connected
    (_ANY_WORKFLOW, "not_connected"): DispositionResult("Couldn't reach", "Busy"),
    # Kept outside the client doc: escalation (patient safety) and no_output
    # (connected but nothing usable — distinct from a non-connect).
    (_ANY_WORKFLOW, "escalation"): DispositionResult("Escalation", None),
    (_ANY_WORKFLOW, "no_output"): DispositionResult("No Output", None),
}

_DEFAULT_DISPOSITION = DispositionResult("Follow Up", None)


def resolve_disposition(workflow_code: str, call_outcome: str) -> DispositionResult:
    exact_key = (workflow_code, call_outcome)
    if exact_key in DISPOSITION_MAP:
        return DISPOSITION_MAP[exact_key]
    fallback_key = (_ANY_WORKFLOW, call_outcome)
    if fallback_key in DISPOSITION_MAP:
        return DISPOSITION_MAP[fallback_key]
    return _DEFAULT_DISPOSITION


def is_mapped_outcome(call_outcome: str, workflow_code: str = _ANY_WORKFLOW) -> bool:
    """Whether this outcome has an explicit disposition, rather than the default."""
    return (workflow_code, call_outcome) in DISPOSITION_MAP or (
        _ANY_WORKFLOW,
        call_outcome,
    ) in DISPOSITION_MAP
