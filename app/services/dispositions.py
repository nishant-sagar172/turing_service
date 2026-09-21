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
        "Wants Second Opinion", None
    ),
    # Waiting For Doctor Reports
    (_ANY_WORKFLOW, "waiting_doctor_confirmation"): DispositionResult(
        "Waiting For Doctor Reports", "Doctor OK Pending"
    ),
    (_ANY_WORKFLOW, "waiting_reports"): DispositionResult(
        "Waiting For Doctor Reports", "Report Pending"
    ),
    (_ANY_WORKFLOW, "waiting_referral_letter"): DispositionResult(
        "Waiting for Referral Letter", None
    ),
    # IPD finance / clearance
    (_ANY_WORKFLOW, "insurance_concern"): DispositionResult(
        "Insurance Loan Pending", "Insurance Approval Pending"
    ),
    (_ANY_WORKFLOW, "loan_required"): DispositionResult(
        "Insurance Loan Pending", "Loan Approval Pending"
    ),
    (_ANY_WORKFLOW, "on_medications"): DispositionResult("On Medications", None),
    (_ANY_WORKFLOW, "medical_clearance_pending"): DispositionResult(
        "Medical clearance pending", None
    ),
    # Follow Up
    (_ANY_WORKFLOW, "follow_up"): DispositionResult("Follow Up", None),
    (_ANY_WORKFLOW, "call_dropped"): DispositionResult("Follow Up", None),
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


# Temporary: pre-Kalaam coarse labels, served alongside the current ones.
_LEGACY_DISPOSITION_MAP: dict[tuple[str, str], DispositionResult] = {
    (_ANY_WORKFLOW, "escalation"): DispositionResult("Escalation", None),
    (_ANY_WORKFLOW, "completed_visited"): DispositionResult("Converted", "Visited"),
    (_ANY_WORKFLOW, "scheduled_booking"): DispositionResult(
        "Converted", "Booking Scheduled"
    ),
    ("ipd", "done_elsewhere"): DispositionResult(
        "Not Interested", "Admitted Elsewhere"
    ),
    (_ANY_WORKFLOW, "done_elsewhere"): DispositionResult(
        "Not Interested", "Done Elsewhere"
    ),
    (_ANY_WORKFLOW, "declined"): DispositionResult("Not Interested", "Declined"),
    (_ANY_WORKFLOW, "wants_cost_estimate"): DispositionResult(
        "Follow Up", "Cost Estimate Requested"
    ),
    (_ANY_WORKFLOW, "wants_discount"): DispositionResult(
        "Follow Up", "Discount Requested"
    ),
    (_ANY_WORKFLOW, "wants_second_opinion"): DispositionResult(
        "Follow Up", "Second Opinion"
    ),
    (_ANY_WORKFLOW, "waiting_doctor_confirmation"): DispositionResult(
        "Follow Up", "Doctor Confirmation Pending"
    ),
    (_ANY_WORKFLOW, "follow_up"): DispositionResult("Follow Up", "General Follow Up"),
    (_ANY_WORKFLOW, "call_dropped"): DispositionResult("Follow Up", "Call Dropped"),
    (_ANY_WORKFLOW, "insurance_concern"): DispositionResult(
        "Follow Up", "Insurance/TPA Pending"
    ),
    (_ANY_WORKFLOW, "loan_required"): DispositionResult(
        "Follow Up", "Loan/EMI Required"
    ),
    (_ANY_WORKFLOW, "on_medications"): DispositionResult("Follow Up", "On Medications"),
    (_ANY_WORKFLOW, "waiting_reports"): DispositionResult(
        "Follow Up", "Reports Pending"
    ),
    (_ANY_WORKFLOW, "medical_clearance_pending"): DispositionResult(
        "Follow Up", "Medical Clearance Pending"
    ),
    (_ANY_WORKFLOW, "waiting_referral_letter"): DispositionResult(
        "Follow Up", "Referral Letter Pending"
    ),
    (_ANY_WORKFLOW, "not_connected"): DispositionResult("Couldn't Reach", None),
    (_ANY_WORKFLOW, "no_output"): DispositionResult("No Output", None),
}

_LEGACY_DEFAULT_DISPOSITION = DispositionResult("Follow Up", "General Follow Up")


def resolve_legacy_disposition(
    workflow_code: str | None, call_outcome: str | None
) -> DispositionResult | None:
    """Old-format (status, sub_status) for a stored outcome; None if unclassified."""
    if not call_outcome:
        return None
    return (
        _LEGACY_DISPOSITION_MAP.get((workflow_code or _ANY_WORKFLOW, call_outcome))
        or _LEGACY_DISPOSITION_MAP.get((_ANY_WORKFLOW, call_outcome))
        or _LEGACY_DEFAULT_DISPOSITION
    )


_LEGACY_OUTCOME_BY_CALL_OUTCOME: dict[str, str] = {
    "completed_visited": "booking",
    "scheduled_booking": "booking",
    "escalation": "escalation",
    "done_elsewhere": "not_interested",
    "declined": "not_interested",
    "no_output": "no_output",
    "not_connected": "not_reached",
}


def resolve_legacy_outcome(call_outcome: str | None) -> str | None:
    """Old coarse `outcome` bucket for a stored call_outcome; None if unclassified."""
    if not call_outcome:
        return None
    return _LEGACY_OUTCOME_BY_CALL_OUTCOME.get(call_outcome, "follow_up")
