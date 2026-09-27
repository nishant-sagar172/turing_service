# Disposition Alignment (turing ↔ Kalaam) — Pending

Source of answers: Kalaam `ai_voice_calling_new_pipeline` (committed code).

## How Kalaam uses turing's result
Kalaam sets the patient's status from **`call_outcome` + `workflow_code`** via its own `voice_outcome_dispositions` table and status **codes**. turing's `disposition_status` / `sub_status` strings are stored and shown on Kalaam's voice screens only — they never decide the status written.
- `call_outcome` codes must stay stable. An outcome Kalaam doesn't know is skipped and logged (`skipped_unknown_outcome`); a new outcome needs a Kalaam mapping row first.
- If the mapped status isn't set up in the patient's workflow, Kalaam leaves the status unchanged and logs `skipped_invalid_status` (no error).

## Webhook contract — verified against Kalaam code (`7acfacef`)
- Outcome codes: Kalaam's `voice_outcome_kinds` has exactly turing's 19 codes. Workflow codes match (`opd`, `ipd`, `cancer_workflow`, `gynae_workflow`).
- Receiver `POST /internal/turing/call-completed`; reads `voice_call_id` (top level), nested `analysis.*`, top-level `client_ref` / `patient_uhid` — all as turing sends them.
- Signature: `X-Webhook-Signature: sha256=<hmac-sha256 hex of raw body>` — same scheme as turing.
- **Deploy config (both sides must match):** Kalaam's `TURING_WEBHOOK_SECRET` defaults to empty, which **skips signature checks**. Set it in Kalaam prod and set the same value as the client's `webhook_secret` in turing.
- **Legacy fields are still consumed:** Kalaam's call-list filters fall back to `analysis.outcome` / `legacy_disposition_status` / `legacy_sub_status`. Do not remove turing's legacy layer until Kalaam drops that fallback.

## Resolved
- **Exact strings** — turing's labels match Kalaam's status names (migration 0019). No `Declined` status: a declined call is `Not Interested / Other`.
- **Repeated sub-status** — none; `null` is correct (null, missing and `""` are all accepted).
- **`call_dropped`** — Follow Up / null (unchanged, correct).
- **`no_output`** — Kalaam has no "No Output" status and writes Follow Up → turing now sends Follow Up / null (migration 0019).
- **`escalation`** — Kalaam writes no status (timeline entry only). The "Escalation" label is display-only; kept.
- **Per-client wording** — not needed in turing: Kalaam keys on codes and maps per client itself. Only display labels can drift from a client's renamed statuses.
- **Missing `workflow_code`** — never reject; treat as `opd` (current behaviour).
- **On Medications / Medical Clearance Pending** — only IPD has them in Kalaam → IPD-only in turing is correct.
- **Free-text language** — `summary`, `reason`, `requests`, `symptoms_reported` always in English.

## Open — turing product decisions
1. **gynae_workflow outcome set.** Kalaam's gynae workflow has Insurance / Loan pending (both subs), Cost Help, Wants second opinion and Waiting for doctor / reports, but turing offers gynae only the common set → turing can never return `insurance_concern`, `loan_required` or `waiting_reports` for gynae. Decide whether to add them.
2. **Waiting for Reports outside IPD.** Kalaam accepts it for any workflow; it saves for ipd/gynae patients and is safely skipped for opd/cancer. Note: an IPD-workflow patient on a non-admission task is sent to turing as `opd`, so IPD-only outcomes are withheld from a patient whose workflow has them.

## Open — needs a Kalaam change
3. **Not-connected reasons.** Kalaam's Couldn't Reach has sub-statuses (Busy, Switch Off, No Number, Wrong Number, Invalid Number, RNR, Closed Inquiry, Call Later — varies by workflow), but maps every `not_connected` to Busy. Using the real reason needs new outcome codes (e.g. `not_connected_no_answer` → RNR) plus Kalaam mapping rows. `balance-low` is an account problem and should not change the patient's status.

## For the Kalaam team (their side, FYI)
- **Escalation has no alert.** An `escalation` call only gets a timeline entry: no ticket, no status, and nothing acts on `urgency = high`. Patient-safety gap.
- **Inconsistent `workflow_code`.** Auto-call sends the patient's workflow as-is (an ipd patient → `ipd` even for a follow-up); campaigns/flows turn non-admission ipd tasks into `opd`. Same patient, different outcome sets.
- **`ip_admission` in opd/gynae** is sent as `ipd`, but those workflows lack most IPD statuses → those outcomes are skipped.
- **gynae / cancer Not Interested** has no `Other` / `Done Elsewhere` children, so declined / done-elsewhere calls lose their sub-status there.
- **Auto-call batch payload is wrong** (`voice_auto_call_tasks.py:164-182`): sends `phone_number` + `variables` + singular `from_phone_number`; turing needs flat `contact_number` and a `from_phone_numbers` list → 422. Also no `client_ref`, and UTC schedule with microseconds.
- **Outcomes can be silently lost** (`voice_call_tasks.py:982`): any exception mentioning "voice_call" is swallowed as "tables missing", after the webhook already returned 200.
- **Reconcile reads the wrong fields from `GET /v1/calls/{id}`**: it expects raw-execution keys (`id`/`execution_id`, `total_cost`, `conversation_duration`, `telephony_data`, `context_details`), but turing returns `call_id`, `cost`, `duration`. Cost/duration stay unset on reconciled calls.
- **Single calls send no `client_ref`** — matching relies on `execution_id` being committed before the webhook (race handled by an orphan-adoption path).
- **Webhook 400s are permanent** (non-JSON, missing execution id): turing retries any non-2xx for up to 7 days. turing always sends both fields, so low risk today.

## When an open item is decided
1. `app/services/workflows.py` (outcome membership) and/or `app/services/dispositions.py` (strings).
2. New data migration for existing rows — never edit applied migrations.
3. The prompt's disposition reference regenerates from the mapping; change outcome definitions only if outcomes are added/removed (and coordinate the code with Kalaam first).
4. `docs/integration-guide.html`, `frontend/lib/outcomes.ts`.
5. Re-verify on a real DB: backfill, a fresh classification, the webhook payload.
