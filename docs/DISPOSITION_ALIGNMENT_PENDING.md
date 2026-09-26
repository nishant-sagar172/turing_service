# Disposition Alignment (turing ↔ Kalaam) — Pending

**Status: pending.** turing currently ships the behaviour described under "Current" for each item. Clients match on `disposition_status` / `sub_status`, so each must end up identical to Kalaam (spelling, casing, punctuation).

## Waiting on Kalaam

### Q1. Sub Status for four outcomes
The Call-Outcome guide repeats the status as the Sub Status; migration `0017_dispositions_match_kalaam` set these to NULL because Kalaam reportedly has no child status.

| Call Outcome | Guide | Current (turing) |
|---|---|---|
| Want / went for second opinion | Wants Second Opinion / Wants Second Opinion | Wants Second Opinion / — |
| On medications (IPD) | On Medications / On Medications | On Medications / — |
| Medical clearance pending (IPD) | Medical clearance pending / Medical clearance pending | Medical clearance pending / — |
| Waiting for referral letter | Waiting for Referral Letter / Waiting for Referral Letter | Waiting for Referral Letter / — |

Needed: does Kalaam define a child status for each, and its exact value?

### Q2. turing outcomes not in the guide
| Outcome | Meaning | Current (turing) |
|---|---|---|
| `escalation` | Active/worsening symptom, adverse drug reaction, urgent callback | Escalation / — |
| `call_dropped` | Conversation began, call cut off without a conclusion | Follow Up / — |
| `no_output` | Connected but nothing usable (wrong number, voicemail, silence, no transcript) | No Output / — |

Needed: does Kalaam accept `Escalation` and `No Output`? If not, which existing status/sub status should each map to?

### Q3. "Not connected" sub status
Guide: `Couldn't reach / Busy` for every non-connect. turing receives distinct engine statuses (`no-answer`, `busy`, `failed`, `canceled`, `stopped`, `error`, `balance-low`) and currently sends `Busy` for all.

Needed: `Busy` for all, or separate sub statuses (e.g. No Answer, Switched Off)?

### Q4. Exact strings
- `Couldn't reach`: guide uses a curly apostrophe (`’`); turing sends a straight one (`'`). String comparison treats these as different.
- Casing of `Couldn't reach` and `Medical clearance pending` (lowercase words, unlike the others).

Needed: the canonical characters Kalaam uses.

## Accepted for now — revisit later

### Q5. Task Type → workflow
- turing workflows: `opd`, `ipd`, `cancer_workflow`, `gynae_workflow`. The guide has two tables: IPD and Other.
- **Current:** `cancer_workflow` and `gynae_workflow` follow the "Other" table; a call with no Task Type (and no client default) uses `opd` ("Other").
- **Risk:** an IPD call sent without `workflow_code=ipd` can never return insurance, loan, medications, clearance or reports outcomes.
- To do: confirm the cancer/gynae mapping with Kalaam, and decide whether a missing Task Type should be an error, a per-client default, or stay `opd`.

## Decided
- **D1. Free-text language:** `summary`, `reason`, `requests` and `symptoms_reported` are always written in English, whatever language the call is in (prompt + output schema updated).

## When Q1–Q4 are answered
1. Set exact strings in `app/services/dispositions.py`.
2. Add a new data migration (`0019`) to re-map existing rows — never edit applied migrations.
3. Change the analysis prompt only if Q2 removes or merges outcomes.
4. Update `docs/integration-guide.html` and `frontend/lib/outcomes.ts`.
5. Re-verify on a real DB: backfill, a fresh classification, and the webhook payload.
