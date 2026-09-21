"""Disposition mapping vs the Kalaam "Call Outcome & Disposition Guide".

`resolve_disposition` is what turns the classifier's call_outcome into the
(status, sub_status) pair Kalaam stores, so these tests pin it to the guide.

A guide sub-status that just repeats its status (On Medications / On
Medications) is expressed as None: Kalaam has no child status for it and fills
the sub-status in as the status itself (migration 0017 clears stored rows).
"""

from __future__ import annotations

import pytest

from app.services.dispositions import (
    DISPOSITION_MAP,
    is_mapped_outcome,
    resolve_disposition,
    resolve_legacy_disposition,
    resolve_legacy_outcome,
)
from app.services.workflows import (
    NOT_CONNECTED_OUTCOME,
    outcomes_for_workflow,
)

# call_outcome -> (Disposition Status, Sub Status), IPD table.
IPD_GUIDE: dict[str, tuple[str, str | None]] = {
    "completed_visited": ("Visited", None),
    "scheduled_booking": ("Booking", None),
    "done_elsewhere": ("Not Interested", "Admitted Elsewhere"),
    "wants_cost_estimate": ("Cost Help", "Waiting Estimate"),
    "wants_discount": ("Cost Help", "Discount Asked"),
    "insurance_concern": ("Insurance Loan Pending", "Insurance Approval Pending"),
    "loan_required": ("Insurance Loan Pending", "Loan Approval Pending"),
    "wants_second_opinion": ("Wants Second Opinion", None),
    "on_medications": ("On Medications", None),
    "waiting_doctor_confirmation": ("Waiting For Doctor Reports", "Doctor OK Pending"),
    "waiting_reports": ("Waiting For Doctor Reports", "Report Pending"),
    "medical_clearance_pending": ("Medical clearance pending", None),
    "waiting_referral_letter": ("Waiting for Referral Letter", None),
    "follow_up": ("Follow Up", None),
    "declined": ("Declined", "Other"),
    "not_connected": ("Couldn't reach", "Busy"),
}

# The guide's "Other Tasks" table drops the admission-only outcomes and says
# "Done Elsewhere" instead of "Admitted Elsewhere".
IPD_ONLY = {
    "insurance_concern",
    "loan_required",
    "on_medications",
    "waiting_reports",
    "medical_clearance_pending",
}
OTHER_GUIDE: dict[str, tuple[str, str | None]] = {
    outcome: pair for outcome, pair in IPD_GUIDE.items() if outcome not in IPD_ONLY
}
OTHER_GUIDE["done_elsewhere"] = ("Not Interested", "Done Elsewhere")

OTHER_WORKFLOWS = ["opd", "cancer_workflow", "gynae_workflow"]


@pytest.mark.parametrize("outcome", sorted(IPD_GUIDE))
def test_ipd_outcome_maps_to_the_guide(outcome: str) -> None:
    result = resolve_disposition("ipd", outcome)
    assert (result.status, result.sub_status) == IPD_GUIDE[outcome]


@pytest.mark.parametrize("workflow_code", OTHER_WORKFLOWS)
@pytest.mark.parametrize("outcome", sorted(OTHER_GUIDE))
def test_other_task_outcome_maps_to_the_guide(workflow_code: str, outcome: str) -> None:
    result = resolve_disposition(workflow_code, outcome)
    assert (result.status, result.sub_status) == OTHER_GUIDE[outcome]


def test_done_elsewhere_is_the_only_outcome_that_differs_by_workflow() -> None:
    for outcome in OTHER_GUIDE:
        ipd = resolve_disposition("ipd", outcome)
        opd = resolve_disposition("opd", outcome)
        assert (ipd == opd) is (outcome != "done_elsewhere")


@pytest.mark.parametrize("workflow_code", ["ipd", *OTHER_WORKFLOWS])
def test_the_guide_outcomes_are_all_ones_the_workflow_can_produce(
    workflow_code: str,
) -> None:
    guide = IPD_GUIDE if workflow_code == "ipd" else OTHER_GUIDE
    producible = outcomes_for_workflow(workflow_code) | {NOT_CONNECTED_OUTCOME}
    assert set(guide) <= producible


@pytest.mark.parametrize("workflow_code", OTHER_WORKFLOWS)
def test_admission_only_outcomes_are_never_offered_outside_ipd(
    workflow_code: str,
) -> None:
    assert not IPD_ONLY & outcomes_for_workflow(workflow_code)
    assert IPD_ONLY <= outcomes_for_workflow("ipd")


def test_outcomes_beyond_the_guide_are_the_documented_extras() -> None:
    mapped = {outcome for (_, outcome) in DISPOSITION_MAP}
    assert mapped - set(IPD_GUIDE) == {"escalation", "call_dropped", "no_output"}
    assert resolve_disposition("ipd", "escalation") == ("Escalation", None)
    assert resolve_disposition("ipd", "call_dropped") == ("Follow Up", None)
    assert resolve_disposition("ipd", "no_output") == ("No Output", None)


def test_an_unknown_outcome_falls_back_to_follow_up_and_is_reported_unmapped() -> None:
    assert resolve_disposition("ipd", "brand_new_outcome") == ("Follow Up", None)
    assert not is_mapped_outcome("brand_new_outcome")
    assert is_mapped_outcome("declined")


@pytest.mark.parametrize(
    ("workflow", "outcome", "expected"),
    [
        ("opd", "scheduled_booking", ("Converted", "Booking Scheduled")),
        ("ipd", "done_elsewhere", ("Not Interested", "Admitted Elsewhere")),
        ("opd", "declined", ("Not Interested", "Declined")),
        ("ipd", "call_dropped", ("Follow Up", "Call Dropped")),
        ("opd", "not_connected", ("Couldn't Reach", None)),
        ("opd", "unknown_outcome", ("Follow Up", "General Follow Up")),
    ],
)
def test_legacy_disposition(
    workflow: str, outcome: str, expected: tuple[str, str | None]
) -> None:
    assert resolve_legacy_disposition(workflow, outcome) == expected


def test_legacy_disposition_unclassified_is_none() -> None:
    assert resolve_legacy_disposition("opd", None) is None


@pytest.mark.parametrize(
    ("call_outcome", "expected"),
    [
        ("scheduled_booking", "booking"),
        ("completed_visited", "booking"),
        ("escalation", "escalation"),
        ("declined", "not_interested"),
        ("done_elsewhere", "not_interested"),
        ("no_output", "no_output"),
        ("not_connected", "not_reached"),
        ("wants_discount", "follow_up"),
        (None, None),
    ],
)
def test_legacy_outcome(call_outcome: str | None, expected: str | None) -> None:
    assert resolve_legacy_outcome(call_outcome) == expected
