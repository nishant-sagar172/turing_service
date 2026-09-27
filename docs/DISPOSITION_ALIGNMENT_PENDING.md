# Disposition Alignment (turing ↔ Kalaam) — Pending

Clients match on `disposition_status` / `sub_status`, so they must be identical to Kalaam's status names (spelling, casing, `/`, apostrophe).

## Resolved (from Kalaam's status table — applied in migration 0019)
- **Q1. Sub Status that repeats its status** → none. Wants second opinion, On Medications, Medical Clearance Pending and Waiting for Referral Letter have no sub-status.
- **Q3. Not connected** → `Couldn't Reach / Busy` for every non-connect.
- **Q4. Exact strings** → Kalaam values, e.g. `Insurance / Loan pending`, `Waiting for doctor / reports`, `Waiting estimate`, `Couldn't Reach` (capital R, straight apostrophe). There is no `Declined` status: a declined call is `Not Interested / Other`.
- **D1. Free-text language** → `summary`, `reason`, `requests`, `symptoms_reported` always in English.

## Still open

### Q2. turing outcomes not in Kalaam's table
| Outcome | Meaning | Current (turing) |
|---|---|---|
| `escalation` | Active/worsening symptom, adverse drug reaction, urgent callback | Escalation / — |
| `call_dropped` | Conversation began, call cut off without a conclusion | Follow Up / — |
| `no_output` | Connected but nothing usable (wrong number, voicemail, silence, no transcript) | No Output / — |

Needed: does Kalaam have `Escalation` and `No Output` statuses? If not, which existing status/sub-status should each map to?

### Q5. Task Type → workflow
- turing workflows: `opd`, `ipd`, `cancer_workflow`, `gynae_workflow`. **Current:** cancer/gynae follow the "Other" table; a call with no Task Type (and no client default) uses `opd`.
- **Risk:** an IPD call sent without `workflow_code=ipd` can never return insurance, loan, medications, clearance or reports outcomes.
- To do: confirm cancer/gynae mapping; decide whether a missing Task Type should be an error, a per-client default, or stay `opd`.

### Q6. Which outcomes are offered outside IPD
Kalaam applies every outcome to every task type (it only fails if that task type lacks the status). turing currently offers these **only for IPD**: Insurance Related Concern, Loan Options Required, On Medications, Medical Clearance Pending, **Waiting for Reports**.
- **Waiting for Reports** is missing from the guide's Other Tasks table but valid in Kalaam for every task type. Decide: offer it for OPD/other workflows too, or keep it IPD-only on purpose.
- The other four: keeping them IPD-only matches the guide's staff advice.

## When an open item is decided
1. Set exact strings in `app/services/dispositions.py` (and outcome membership in `app/services/workflows.py` for Q6).
2. Add a new data migration to re-map existing rows — never edit applied migrations.
3. The prompt's disposition reference is generated from the mapping, so it updates itself; change outcome definitions only if Q2 removes or merges outcomes.
4. Update `docs/integration-guide.html` and `frontend/lib/outcomes.ts`.
5. Re-verify on a real DB: backfill, a fresh classification, and the webhook payload.
