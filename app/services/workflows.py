"""Registry of calling workflows.

``workflow_code`` mirrors Kalaam's ``workflows.workflow_code`` — the two must
stay in step, because a batch is created against a Kalaam workflow and its calls
are classified here. Deliberately NOT called "task type": Kalaam uses that for
the clinical task (``medication``, ``lab_test``, ``ip_admission``), and reusing
the name across the boundary invites passing ``ip_admission`` where ``ipd``
belongs.

A workflow decides which call outcomes the classifier may assign and which
outcome definitions get spliced into the system prompt. Adding one means adding
ONE entry here — the outcome set, the prompt section, the schema enum, the
validation pattern and the console dropdown all derive from this registry.

Dependency-free (no app imports) so schemas, services and routers can all read
it without an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

# Outcomes every workflow can produce, whatever its code.
COMMON_OUTCOMES = frozenset(
    {
        "escalation",
        "completed_visited",
        "scheduled_booking",
        "done_elsewhere",
        "wants_cost_estimate",
        "wants_discount",
        "wants_second_opinion",
        "waiting_doctor_confirmation",
        "follow_up",
        "call_dropped",
        "declined",
        "no_output",
    }
)

# Assigned by the status classifier when a call never connected — never offered
# to the LLM, so it is excluded from every workflow's enum.
NOT_CONNECTED_OUTCOME = "not_connected"

_IPD_EXTRA_OUTCOMES = frozenset(
    {
        "insurance_concern",
        "loan_required",
        "on_medications",
        "waiting_reports",
        "medical_clearance_pending",
        "waiting_referral_letter",
    }
)

_IPD_PROMPT_SECTION = """

- insurance_concern: Decision blocked by insurance/TPA approval or coverage.
  Signals: "insurance se hoga kya", "TPA approval pending", "cashless milega"

- loan_required: Patient needs financing (EMI/medical loan).
  Signals: "EMI ka option hai", "loan mil sakta hai", "installments mein"

- on_medications: Admission deferred — patient on a medication course first.
  Signals: "dawai chal rahi hai", "doctor ne 2 weeks bola hai"

- waiting_reports: Tests done but results not back yet.
  Signals: "reports aane do", "test hua hai results pending", \
"report test karke aana hai"

- medical_clearance_pending: Needs fitness/clearance from another specialist.
  Signals: "cardiac clearance chahiye", "anaesthesia clearance pending"

- waiting_referral_letter: Referral document from insurer still required.
  Signals: "referral letter nahi aaya", "insurer se letter chahiye\""""


@dataclass(frozen=True)
class Workflow:
    code: str
    label: str
    description: str
    extra_outcomes: frozenset[str] = frozenset()
    prompt_section: str = ""

    @property
    def outcomes(self) -> frozenset[str]:
        """Everything the LLM may return for this workflow."""
        return COMMON_OUTCOMES | self.extra_outcomes


WORKFLOWS: dict[str, Workflow] = {
    "opd": Workflow(
        code="opd",
        label="OPD / follow-up",
        description="Out-patient follow-ups, appointment reminders, check-ins.",
    ),
    "ipd": Workflow(
        code="ipd",
        label="IPD admission",
        description="In-patient admission coordination — unlocks finance and "
        "clearance outcomes.",
        extra_outcomes=_IPD_EXTRA_OUTCOMES,
        prompt_section=_IPD_PROMPT_SECTION,
    ),
    # Registered so campaigns can be tagged and reported on today. Their
    # speciality-specific outcomes are not defined yet, so they currently share
    # the common set — add extra_outcomes + prompt_section here when they are.
    "cancer_workflow": Workflow(
        code="cancer_workflow",
        label="Cancer care",
        description="Oncology pathways — currently uses the shared outcome set.",
    ),
    "gynae_workflow": Workflow(
        code="gynae_workflow",
        label="Gynaecology",
        description="Gynaecology pathways — currently uses the shared outcome set.",
    ),
}

# Used when a batch and its client both leave the workflow unset. Every level is
# optional: campaigns run without one and classify against the common outcomes.
DEFAULT_WORKFLOW_CODE = "opd"

VALID_WORKFLOW_CODES = frozenset(WORKFLOWS)

# For Pydantic Field(pattern=...) — regenerated automatically from the registry.
WORKFLOW_CODE_PATTERN = f"^({'|'.join(sorted(VALID_WORKFLOW_CODES))})$"


def resolve(workflow_code: str | None) -> Workflow:
    """Look up a workflow, falling back to the default for unset/unknown codes."""
    if workflow_code and workflow_code in WORKFLOWS:
        return WORKFLOWS[workflow_code]
    return WORKFLOWS[DEFAULT_WORKFLOW_CODE]


def outcomes_for_workflow(workflow_code: str | None) -> frozenset[str]:
    return resolve(workflow_code).outcomes
