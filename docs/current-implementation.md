# AI Voice Calling — Current Implementation (for review)

**Status:** Work in progress, feature-complete on the happy path, one known
open issue (filter parity — see §7). **Zero real phone calls have been placed
during this build** — all verification used fakes, mocks, or read-only Bolna
calls (agent/phone-number listing, credential probes).

**Repos involved:**
| Repo | Path | Role |
|---|---|---|
| turing_service | `C:\Docstribe\turing_service` | Standardized voice-calling micro-service; wraps Bolna |
| Kalaam backend | `C:\Docstribe\kalaam1\kalaam` | Caller; owns patients; stores lean outcomes |
| kalam_frontend | `C:\Docstribe\kalam_frontend` | Operator UI (admin portal) |
| Bolna | `https://api.bolna.ai` (vendor) | Voice-AI platform that places/records calls |

---

## 1. Overview

An operator in Kalaam's admin portal opens **AI Voice Calling**, selects
patients (single patient or a filtered campaign audience — same filter UI as
Task Management), picks a Bolna voice **agent**, maps that agent's required
prompt variables to patient fields, configures retries, and sends. Kalaam's
backend calls **turing** (the standardized micro-service) over an
authenticated internal API; turing validates the request against the agent's
variable contract and places the call(s) via Bolna. As each call completes,
Bolna notifies turing; turing persists the full record and forwards a lean
outcome back to Kalaam, which stores it against the patient.

---

## 2. Architecture

```
┌────────────────┐        ┌──────────────────────┐   X-API-Key   ┌───────────────────┐
│  kalam_frontend │  HTTP  │    Kalaam backend    │  ──────────▶  │   turing_service   │
│  /voice-calls   │ ─────▶ │  /api/v1/voice-calls │               │   /v1/*  (:8005)   │
│  (Next.js :3000)│  cookie│  (FastAPI :8000)     │  ◀──────────  │                    │
└────────────────┘  (JWT) │  turing_client.py     │   HMAC webhook│  own Postgres :5433│
                          │  voice_call_* tables   │               │  batches/calls/logs│
                          │  /internal/turing/...  │               └─────────┬──────────┘
                          └───────────┬────────────┘                         │ HTTPS
                                      │                                       ▼
                             ┌────────▼─────────┐                  ┌───────────────────┐
                             │  kalam-postgres  │                  │   Bolna (vendor)  │
                             │     (:5432)      │                  │   api.bolna.ai    │
                             └──────────────────┘                  └───────────────────┘
```

**Outcome path (event-driven):**
```
Bolna → turing POST /webhooks/bolna (per execution, IP-allowlisted)
  → turing updates its `calls` row (status, transcript, recording, cost)
  → turing POSTs a LEAN outcome to Kalaam (HMAC-SHA256 signed)
    → Kalaam POST /internal/turing/call-completed → enqueues Celery task
      → task upserts voice_call_records (idempotent on turing_execution_id),
        links patient by patient_uhid (fallback: phone digits)
(fallback) Kalaam Celery beat reconciles every 10 min by polling turing
```

The browser never talks to turing directly, and never sees its base URL or
API key — only the Kalaam backend holds those.

---

## 3. turing_service — what's built

**Path:** `C:\Docstribe\turing_service`

### API surface
- All business endpoints under **`/v1/*`**, protected by `X-API-Key`
  (`app/auth.py`, checked in `app/main.py`).
- Every response carries **`X-Request-ID`** (`app/middleware.py`).
- Every error uses one **standard envelope**:
  `{ "error": <code>, "message": <human>, "detail": <any>, "request_id": <id> }`
  (`app/errors.py`) — covers `HTTPException`, validation errors, and
  upstream `BolnaError`s (status code passed through; transport failures → 502).
- `GET /health`, `GET /health/ready` (DB check) are open, unauthenticated.

### Endpoints (`app/routers/`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/bolna/status` | Bolna connectivity/credential probe |
| GET | `/v1/agents` | List Bolna agents |
| GET | `/v1/agents/{id}/variables` | Agent's required/optional prompt variables (read-only prompt scan) |
| GET | `/v1/phone-numbers` | Caller IDs + configured default |
| POST | `/v1/calls` | Single call — validates vars, places via Bolna, persists |
| GET | `/v1/calls/{id}` | Status/transcript/outcome (served from turing's DB; refreshes from Bolna if non-terminal) |
| POST | `/v1/calls/{id}/stop` | Cancel queued/scheduled call |
| POST | `/v1/batches` | Campaign from JSON recipients — validates every row, persists |
| POST | `/v1/batches/{id}/schedule` | Schedule a created batch |
| GET | `/v1/batches/{id}` | Batch status (merged live + persisted) |
| GET | `/v1/batches/{id}/executions` | Per-call rows (also the reconcile path — upserts as it reads) |
| GET | `/v1/batches/{id}/metrics` | Counts / cost / success-rate |
| POST | `/v1/batches/{id}/stop` | Halt batch |
| DELETE | `/v1/batches/{id}` | Delete batch |
| POST | `/webhooks/bolna` | Bolna execution callbacks (IP-allowlist, not client-facing) |

### Datastore (new — turing is stateful)
Dedicated Postgres, own Docker container (`docker-compose.yml`, host port
**5433** — distinct from `kalam-postgres:5432` and `docstribe-infra:5434),
Alembic-managed (`alembic/versions/0001_initial.py`).

- `batches` — id, client, agent_id, from_number, mode, retry_config (jsonb),
  bolna_batch_id (unique), status, total/valid counts, scheduled_at,
  recipients_snapshot (jsonb).
- `calls` — id, batch_id (fk), agent_id, contact_number, patient_ref,
  bolna_execution_id (**unique** — idempotency key), status, transcript,
  recording_url, extracted_data (jsonb), cost, duration, hangup_reason,
  retry_count, raw_payload (jsonb, full Bolna record).
- `request_logs` — request_id, client, method, endpoint, status_code,
  latency_ms (best-effort audit log written by the middleware).

### Variable validation (unchanged core feature)
`app/core/variables.py` / `app/services/variables.py` scan the agent's Bolna
prompt (read-only `GET /v2/agent/{id}`) for `{placeholder}` variables, split
into required/optional (optional list overridable per-agent via
`agent_variables.json`), and reject (`422`) any call/batch-row missing a
required variable. Extra/unused variables are returned as non-blocking
warnings.

### Webhook + forwarding
`app/routers/webhooks.py` receives Bolna's per-execution POST, upserts the
matching `calls` row (`app/services/store.py::upsert_call_from_execution`,
idempotent on `bolna_execution_id`), then `app/services/kalaam_notifier.py`
builds a **lean outcome** and POSTs it to Kalaam with an
`X-Webhook-Signature: sha256=<hmac>` header (secret: `KALAAM_WEBHOOK_SECRET`).
Forwarding failures are logged, never raised — the Bolna webhook is always
ACKed; Kalaam's reconcile poll covers anything missed.

---

## 4. Kalaam backend — what's built

**Path:** `C:\Docstribe\kalaam1\kalaam`

### New tables (fully separate from existing features)
Migration `migrations/versions/voice_calls_001_create_voice_call_tables.py`
(applied and stamped in the live `continental-pilot-local` DB):

- **`voice_call_batches`** — id, created_by_id (fk users), agent_id,
  agent_name, mode (single|campaign), turing_batch_id (unique), retry_config
  (jsonb), variable_mapping (jsonb), audience (jsonb snapshot), total_count,
  status, scheduled_at.
- **`voice_call_records`** — id, batch_id (fk), patient_id (fk patients,
  nullable), patient_uhid, contact_number, agent_id, turing_execution_id
  (**unique** — idempotency key), status, disposition, recording_url, cost,
  duration, hangup_reason, variables (jsonb), turing_ref (jsonb, full lean
  payload), error_message.

Model: `app/models/voice_call.py`. **Nothing is written to
`patient_call_records` or any Acefone/WhatsApp table** — this was an explicit
requirement (own vertical, own tables).

### turing client
`app/services/turing_client.py` (`TuringClient` + `TuringAPIError`) — mirrors
the existing `AcefoneClient` pattern: httpx, `X-API-Key` header, settings-driven
base URL/timeout, surfaces turing's `X-Request-ID` on failures for tracing.

### Endpoints (`app/api/v1/endpoints/voice_calls.py`, mounted at `/api/v1/voice-calls`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/agents` | Proxy → turing agent list |
| GET | `/agents/{id}/variables` | Proxy → turing variable contract |
| GET | `/phone-numbers` | Proxy → turing caller IDs |
| POST | `/single` | Resolve one patient's phone + variables → turing `/v1/calls` → pending `voice_call_records` row |
| POST | `/batch` | Resolve N patients → turing `/v1/batches` → `voice_call_batches` + pending records |
| POST | `/batches/{id}/schedule` | Proxy → turing schedule |
| GET | `/batches`, `/batches/{id}` | List/detail with per-patient records, for the history panel |

Phone resolution follows Kalaam's standard order:
`phone → phone_captured → secondary_phone`, normalized to E.164.
`patient_uhid` is attached to every recipient so outcomes link back
deterministically (round-trips through Bolna's
`context_details.recipient_data`).

### Inbound webhook + Celery
- `app/api/internal/turing_webhook.py` — `POST /internal/turing/call-completed`,
  HMAC-SHA256 verified (secret `TURING_WEBHOOK_SECRET`, same pattern as the
  existing WhatsApp webhook verifier), ACKs fast, enqueues Celery.
- `app/workers/voice_call_tasks.py`:
  - `process_turing_call_outcome` — **idempotent upsert** on
    `turing_execution_id`; claims the pre-created pending row by
    `(batch_id, patient_uhid|contact_number)` when the execution id isn't
    known yet; links `patient_id` by uhid, falls back to last-10-digit phone
    match; **never downgrades a terminal status** (guards against a stale
    reconcile racing behind a webhook); auto-marks the parent batch
    `completed` once every record is terminal.
  - `reconcile_voice_call_outcomes` — Celery-beat task (every
    `VOICE_CALL_RECONCILE_INTERVAL_MINUTES`, default 10) that polls turing for
    active batches' executions and pending single sends, covering missed
    webhooks / local dev where turing isn't publicly reachable.
- Both registered in `app/core/celery.py` (`include`, `task_routes`, beat
  schedule).

### Config additions
`app/core/config.py`: `TURING_BASE_URL`, `TURING_API_KEY`,
`TURING_WEBHOOK_SECRET`, `TURING_HTTP_TIMEOUT_SECONDS`,
`VOICE_CALL_RECONCILE_INTERVAL_MINUTES`.

---

## 5. kalam_frontend — what's built

**Path:** `C:\Docstribe\kalam_frontend`

### Routing
- Page: `app/(protected)/voice-calls/page.tsx` → **`/voice-calls`**
  (`?mode=single|campaign`).
- Sidebar entry **"AI Voice Calling"** added to `lib/navigation-config.ts`
  (previously the feature existed but had no nav link — fixed).
- BFF proxy: `app/api/voice-calls/[...path]/route.ts` → Kalaam backend
  `/api/v1/voice-calls/*` (cookie-forwarding, same pattern as every other
  feature's proxy — the browser only ever calls same-origin `/api/*`).

### Components (`components/voice-calls/`)
- `VoiceBatchWizard.tsx` — campaign flow: **Audience → Agent & Variables →
  Retries → Review → Done**.
- `VoiceSingleSend.tsx` — single-call flow (same steps, one patient).
- `AgentVariablesStep.tsx` — agent picker + caller-ID picker + a **dynamic
  variable-mapping form** driven by turing's live `GET /agents/{id}/variables`
  contract (map each required variable to a patient field or a fixed value).
- `RetryConfigForm.tsx` — full Bolna `retry_config` editor (max retries,
  intervals, retry-on statuses, retry-on-voicemail).
- `VoicePatientTable.tsx` — patient rows for pick/select.
- `VoiceAudienceFilters.tsx` — workflow tabs + department/doctor + task-type
  and status chips.
- `VoiceBatchHistoryPanel.tsx` — reads `voice_call_batches`/`records` only
  (never Saheli/Acefone history) — per-batch expand shows call-level
  status/duration/cost/recording.

### Data / services
- `lib/services/voice-calls.service.ts` — typed client for all
  `/api/voice-calls/*` calls.
- `lib/hooks/useVoiceCalls.ts` — TanStack Query hooks (agents, agent
  variables, phone numbers, batches, single-send/campaign mutations with
  toast feedback).
- `lib/hooks/useVoiceAudience.ts` — **audience selection**, described below.

### Audience selection — reuse of the Task Management pipeline
Rather than reinvent patient filtering, `useVoiceAudience` composes the
**existing, battle-tested Task Management hooks and endpoints** directly:
`useWorkflowBuckets`, `useWorkflowCounts`, `useFilterDefaults`,
`usePatientData`, `useDepartmentDoctorOptions`, hitting the shared
`/api/patients`, `/api/patients/counts`, `/api/workflow/buckets` endpoints —
identical to what Task Management uses. This means:
- **Same RBAC/scoping as Task Management** — an `admin`-role login sees all
  patients (verified live: 19,032 matching OPD/follow-up/FRESH); a scoped role
  like `calling_agent` only sees their own (verified: near-zero).
- **Same data**, no duplicated query logic to drift out of sync.

An earlier iteration built voice-specific `/voice-calls/audience/*` backend
endpoints delegating to the WhatsApp-send (`wa_send.py`) filter logic instead
— this was found to be inconsistent (its `patients.total` is not a true grand
total, and status/task-type filtering didn't reliably narrow the list) and
was replaced with the Task Management pipeline described above. The unused
`wa_send`-delegating endpoints in `voice_calls.py` are dead code pending
cleanup.

---

## 6. What's verified

All verification was **read-only, simulated, or against fakes/mocks — no real
phone calls were placed** at any point in this build.

- **turing (28/28 offline checks):** `/v1` versioning, `X-API-Key` enforcement
  (401 without), request-ID + error envelope on every failure mode (401, 422,
  upstream 404/500), variable validation, persistence on create, webhook
  simulation (payload → row update → signed forward, HMAC verified), webhook
  idempotency on redelivery, metrics endpoint math.
- **Kalaam (20/20 E2E checks)** against the **live** patient Postgres
  (27k+ real patients) with a mock turing standing in for Bolna:
  JWT-gated trigger endpoints, campaign payload construction (E.164 phone +
  patient_uhid + variable mapping + retry_config forwarded correctly),
  pending-row creation, HMAC callback acceptance + bad-signature rejection,
  Celery claim-and-upsert of the pending row, idempotent redelivery (no
  duplicate rows), single send, ghost-execution handling (unknown execution
  still creates a linked record), reconcile-poll completing a second patient
  and auto-marking the batch `completed`, list/detail monitoring endpoints.
- **Live Bolna connectivity** confirmed via `GET /v1/bolna/status` (real
  account, real wallet balance) — read-only, no calls.
- **Admin vs. scoped-role patient visibility** confirmed live: admin token →
  19,032 matching patients; `calling_agent` token → near-zero (their own
  assigned set only) — this is Kalaam's existing RBAC, working as designed,
  not new code.

---

## 7. Known open issues

1. ~~Filter/tab parity with Task Management~~ — **resolved.** `useVoiceAudience`
   now mirrors Task Management's per-workflow tab rule exactly: OPD defaults
   to patient view with a manual patient/task toggle (matching the real
   page), IPD is patient-view only (no Task Type row, matching the canonical
   `TaskManagementFilters.tsx` render branches), Gynae is forced to task view.
   Status chips use the same source selection as `page.tsx`'s ternary —
   `computeStatusItems` in patient view, `computeStatusesForCategory` in task
   view gated on a task type being selected (empty row otherwise, not an
   all-types aggregate). Verified live via the Next.js `/api/patients` and
   `/api/patients/counts` proxy (the exact path the browser calls) for all
   three workflow/tab combinations — counts and list totals match.
2. **`/api/patients/counts` latency (~4.5s)** under the full admin-scope
   dataset — acceptable but noticeable; a lighter cached counts path may be
   worth adding later if this becomes a UX complaint.
3. **Dead code:** the earlier `wa_send`-delegating
   `/voice-calls/audience/*` endpoints in Kalaam's `voice_calls.py` are
   unused now that the frontend reads `/api/patients` directly — should be
   removed in a follow-up cleanup pass.

### Explicitly deferred (agreed earlier, not gaps)
- **turing-sdk**: extracting Kalaam's hand-written `turing_client.py` into a
  reusable pip-installable package — deferred until a second platform
  integrates with turing.
- **LLM transcript analytics** (disposition/urgency/health-signal extraction,
  reusing `demo_call_analyzer`) — later phase; turing currently stores raw
  transcript + basic metrics only.
- **Per-client API keys** — a single shared `X-API-Key` is used for now.
- **Multi-tenant webhook routing** — turing forwards to one configured
  Kalaam webhook URL; no per-client routing yet.

---

## 8. Security notes

- **Service auth:** Kalaam → turing calls carry `X-API-Key`; the key and
  turing's base URL live only in Kalaam's backend env — never reach the
  browser (standard BFF proxy pattern, same as every other Kalaam feature).
- **Webhook integrity:** both webhook hops (Bolna → turing is IP-allowlisted;
  turing → Kalaam is HMAC-SHA256 signed) are verified before processing.
  Signature secrets (`KALAAM_WEBHOOK_SECRET` / `TURING_WEBHOOK_SECRET`) are
  separate from the API key.
  - ⚠️ Note for review: as implemented, an unset webhook secret on the Kalaam
    side **logs a warning but does not reject** the request (mirrors the
    existing WhatsApp webhook's dev-mode behavior). This should be confirmed
    as intentional for prod, or hardened to fail closed.
- **No real-call safeguard:** both the single-send and campaign UI flows
  require an explicit "I understand this will place a real AI voice call…"
  checkbox before the Send/Launch button is enabled — the only path capable
  of placing a real call is gated behind deliberate operator confirmation.
- **Data isolation:** voice call data lives exclusively in
  `voice_call_batches`/`voice_call_records` (Kalaam) and `batches`/`calls`
  (turing) — no cross-writes into Acefone or WhatsApp tables.
