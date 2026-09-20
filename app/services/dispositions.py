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
    # ── Escalation (all workflows) ───────────────────────────────────────────
    (_ANY_WORKFLOW, "escalation"): DispositionResult("Escalation", None),
    # ── Converted ─────────────────────────────────────────────────────────────
    (_ANY_WORKFLOW, "completed_visited"): DispositionResult("Converted", "Visited"),
    (_ANY_WORKFLOW, "scheduled_booking"): DispositionResult(
        "Converted", "Booking Scheduled"
    ),
    # ── Not Interested ────────────────────────────────────────────────────────
    # IPD overrides the wording; every other workflow takes the wildcard, so a
    # newly registered workflow still lands on "Not Interested" rather than the
    # generic Follow Up default.
    ("ipd", "done_elsewhere"): DispositionResult(
        "Not Interested", "Admitted Elsewhere"
    ),
    (_ANY_WORKFLOW, "done_elsewhere"): DispositionResult(
        "Not Interested", "Done Elsewhere"
    ),
    (_ANY_WORKFLOW, "declined"): DispositionResult("Not Interested", "Declined"),
    # ── Follow Up ─────────────────────────────────────────────────────────────
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
    # ── IPD-specific follow-ups ───────────────────────────────────────────────
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
    # ── Not connected ─────────────────────────────────────────────────────────
    (_ANY_WORKFLOW, "not_connected"): DispositionResult("Couldn't Reach", None),
    # ── No output ─────────────────────────────────────────────────────────────
    (_ANY_WORKFLOW, "no_output"): DispositionResult("No Output", None),
}

_DEFAULT_DISPOSITION = DispositionResult("Follow Up", "General Follow Up")


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
