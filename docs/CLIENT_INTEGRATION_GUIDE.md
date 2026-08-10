# turing_service — Client Integration Guide

This guide is for developers integrating **your** system with turing, the
voice-calling micro-service that places outbound AI voice campaigns
("batches") on your behalf and reports outcomes back to you.

Scope: this guide covers **registration, authentication, agents, and
batches** — the campaign-placement flow. Single-call endpoints are not
covered here.

---

## 1. Concepts

| Term | Meaning |
|---|---|
| **Client** | Your organization, as registered with turing. Identified by a `client_id` (UUID). |
| **API key** | The credential your backend sends on every request (`X-API-Key`). Yours alone — you never see another client's data. |
| **Agent** | A configured voice-calling persona. turing exposes only the agents an admin has **enabled** for your client. |
| **Batch** | A campaign: one agent, a list of recipients, placed as a set of outbound calls. |
| **Execution** | One call within a batch. |

Everything you create or read through turing is scoped to your `client_id`.
You cannot see, list, or modify another client's batches — referencing one by
id returns `404`, not an error revealing that it exists. Agents work a bit
differently: any `agent_id` that isn't enabled for you (whether it belongs to
another client, doesn't exist, or simply hasn't been turned on for you yet)
returns `403 agent_not_enabled`, not `404` — see §5 and §6.

---

## 2. Base URL

```
https://<your-turing-host>/v1
```

All endpoints below are relative to this base except registration, which is
also under `/v1` (see below), and the outcome webhook, which is not under
`/v1` at all.

The full auto-generated OpenAPI schema is browsable, unauthenticated, at
`<host>/docs` (Swagger UI) and `<host>/openapi.json` — use it to cross-check
exact field types if anything here seems ambiguous.

---

## 3. Onboarding — getting your API key

turing uses self-serve registration followed by admin approval; you cannot
mint your own key.

1. **Register:**

   ```bash
   curl -X POST https://<host>/v1/register \
     -H "Content-Type: application/json" \
     -d '{"name": "Your Company", "contact_email": "eng@yourcompany.com"}'
   ```

   ```json
   { "client_id": "b3f1...-uuid", "status": "pending" }
   ```

   Registering twice with the same `name` returns the same pending record
   rather than erroring — safe to retry. By default, at most 10 registration
   attempts per source IP are accepted per hour (`429 rate_limited` beyond
   that).

2. **Wait for approval.** An operator on turing's side reviews and approves
   your registration out-of-band. On approval, an API key is generated and
   given to you **once** (over a secure channel — it is never retrievable
   again; if lost, ask for a new one to be issued).

3. **Store the key securely.** Treat it like any bearer credential:
   - Send it only over HTTPS, only in the `X-API-Key` header — never in a
     URL query string.
   - Keep it server-side. Do not embed it in mobile or browser code.
   - It is not logged or displayed by turing after issuance.

Until approved, no key exists and every `/v1/*` call you make will fail
authentication.

---

## 4. Authentication

Every request (other than registration) must carry:

```
X-API-Key: tk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

| Situation | Response |
|---|---|
| Header missing | `401 unauthorized` |
| Key invalid/unknown | `401 unauthorized` |
| Key valid, but your client is suspended | `403 forbidden` |

There is no session or token expiry to manage — every request is
authenticated independently. If your key is ever compromised, ask turing's
operator to revoke it and issue a new one.

---

## 5. Error format

Every error response — regardless of endpoint — has the same envelope:

```json
{
  "error": "missing_required_variables",
  "message": "Human-readable summary",
  "detail": { "...": "endpoint-specific structured detail, or null" },
  "request_id": "5286204c5e0747159fd1d83d74d8b2b2"
}
```

Include `request_id` when reporting an issue — it correlates to turing's
server-side logs.

Common `error` codes you'll encounter:

| HTTP | `error` | Meaning |
|---|---|---|
| 401 | `unauthorized` | Missing/invalid `X-API-Key` |
| 403 | `forbidden` | Client suspended |
| 403 | `agent_not_enabled` | The `agent_id` you referenced isn't enabled for your client — this applies whether the agent belongs to another client, doesn't exist, or just hasn't been enabled for you yet. Agents never 404, always this. |
| 404 | `not_found` | No such **batch** for your client (may exist for another client — you can't tell) |
| 422 | `missing_required_variables` | Recipient(s) missing a variable the agent's prompt requires |
| 422 | `validation_error` | Malformed request body |
| 429 | `rate_limited` | Only applies to `/v1/register` |
| 404/405 | `http_error` | Generic Starlette/FastAPI fallback — e.g. a typo'd path or wrong HTTP method that doesn't match any route |
| 502 or passthrough | `voice_engine_error` | The upstream voice engine failed or was unreachable. `502` when the engine couldn't be reached at all; when it *responded* with its own error, that status code (e.g. `400`, `500`) is passed through unchanged instead. |
| 500 | `internal_error` | Unexpected server error |

---

## 6. Agents — discover what you can call with

Agents are configured and enabled for your client by turing's operator. You
only ever see agents that have been explicitly enabled for you.

### `GET /v1/agents`

```bash
curl https://<host>/v1/agents -H "X-API-Key: $KEY"
```

```json
[
  {
    "id": "37768781-4fc4-4df2-a80f-a847b6dad8d2",
    "agent_name": "Booking Agent",
    "agent_status": "processed",
    "display_name": null
  }
]
```

Use `id` as the `agent_id` in every batch request below. If an agent you
expect isn't listed, it isn't enabled for you yet (or was removed upstream —
ask the operator).

### `GET /v1/agents/{agent_id}/variables`

Before sending recipients, check what data the agent's prompt actually
needs — every `required` variable **must** be present per recipient, or your
batch is rejected before anything is placed.

```bash
curl https://<host>/v1/agents/37768781.../variables -H "X-API-Key: $KEY"
```

```json
{
  "agent_id": "37768781-4fc4-4df2-a80f-a847b6dad8d2",
  "required": ["patient_name", "doctors_name", "Follow_Up_Date"],
  "optional": ["Personalised_Symptoms"],
  "system_injected": ["agent_id", "call_sid", "current_date", "current_time",
                       "execution_id", "from_number", "timezone", "to_number"],
  "all_prompt_variables": ["...union of required + optional..."]
}
```

- **`required`** — must be a key on every recipient object you send.
- **`optional`** — may be omitted per-recipient.
- **`system_injected`** — turing/the voice engine supplies these automatically;
  don't send them yourself.

`403 agent_not_enabled` here means the same as elsewhere: this agent isn't
yours to use.

---

## 7. Phone numbers

### `GET /v1/phone-numbers`

```bash
curl https://<host>/v1/phone-numbers -H "X-API-Key: $KEY"
```

```json
{
  "default_from_number": "+91XXXXXXXXXX",
  "phone_numbers": [
    { "id": "...", "phone_number": "+91XXXXXXXXXX", "agent_id": "...", "rented": true }
  ]
}
```

`default_from_number` is what turing uses as caller ID if you omit
`from_phone_numbers` on a batch — either your client's configured default, or
the service-wide fallback. You rarely need to set this explicitly.

> There is currently no self-service endpoint for you to set your own
> `default_from_number` or `webhook_url` (§10) — these are configured for you
> by turing's operator on request. If you need either changed, ask them.

---

## 8. Batches — placing a campaign

A batch is one agent called against a list of recipients. There are two ways
to create one: a **JSON list** (recommended — turing converts it to CSV for
you) or a **raw CSV upload**.

### 8.1 `POST /v1/batches` — create from JSON

```bash
curl -X POST https://<host>/v1/batches \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{
    "agent_id": "37768781-4fc4-4df2-a80f-a847b6dad8d2",
    "recipients": [
      {
        "contact_number": "+919876543210",
        "patient_name": "Asha Rao",
        "doctors_name": "Dr. Mehta",
        "Follow_Up_Date": "2026-07-20"
      }
    ],
    "from_phone_numbers": null,
    "retry_config": {
      "enabled": true,
      "max_retries": 2,
      "retry_on_statuses": ["no-answer", "busy"],
      "retry_intervals_minutes": [15, 60]
    },
    "webhook_url": null
  }'
```

**Request fields:**

| Field | Required | Notes |
|---|---|---|
| `agent_id` | yes | Must be enabled for your client (see §6) |
| `recipients` | yes | Non-empty list of objects. Each **must** include `contact_number` (E.164). Any other key is a prompt variable for that call. |
| `from_phone_numbers` | no | Pool of caller IDs (E.164). Omit to use your configured/default number. |
| `retry_config` | no | Auto-retry behavior for failed calls (all sub-fields optional: `enabled`, `max_retries`, `retry_on_statuses`, `retry_on_voicemail`, `retry_intervals_minutes`). Each value in `retry_intervals_minutes` **must be ≥ 15** — this is the voice engine's own minimum. turing validates it and returns `422 validation_error` up front if violated, so you never get a passthrough `voice_engine_error` for this specific case. |
| `webhook_url` | no | **Leave unset unless you specifically need this.** See warning below. |

> **`webhook_url` replaces turing as the callback target — it does not add a
> second destination.** By default turing tells the voice engine to send
> execution updates to its own receiver (`/webhooks/voice`), which is how
> turing populates `GET .../executions`, keeps its own records current, and
> forwards you the signed outcome described in §10. If you set `webhook_url`
> yourself, the voice engine sends its **raw, unsigned** execution payload
> **directly to your URL instead** — turing never receives it for that batch.
> Concretely, if you set this: you will *not* get turing's signed §10 push for
> this batch's calls, and turing's own DB won't reflect new statuses until you
> next call `GET /v1/batches/{batch_id}/executions` (which still works — it
> polls the voice engine directly, independent of any webhook). Only set this
> field if you specifically want the voice engine's raw callback instead of
> turing's normalized, signed one.

**Validation (before anything is placed):** every recipient is checked
against the agent's variable contract. If any recipient is missing a
`required` variable, the **entire batch is rejected** with `422` and no
calls are placed:

```json
{
  "error": "missing_required_variables",
  "message": "missing_required_variables",
  "detail": {
    "error": "missing_required_variables",
    "agent_id": "37768781-4fc4-4df2-a80f-a847b6dad8d2",
    "required": ["patient_name", "doctors_name", "Follow_Up_Date"],
    "optional": [],
    "rows": [{"row": 3, "missing": ["Follow_Up_Date"]}]
  },
  "request_id": "..."
}
```

(`detail` mirrors the full structured error turing raised internally, hence
the repeated `error` key — read `error`/`message` at the top level, and
`detail.rows` for exactly which recipients failed and why.)

Fix the flagged rows and resend. You can opt out of this check with
`?validate=false` on the request, but then a malformed recipient fails
silently on the voice engine's side instead of being caught up front — not
recommended.

**Success response (`201`):**

```json
{
  "batch_id": "b_abc123",
  "state": "created",
  "warnings": ["variable 'nickname' was sent but the agent's prompt does not use it"]
}
```

`warnings` are non-blocking — extra fields you sent that the agent's prompt
doesn't reference. `batch_id` is what you use for every endpoint below.

> **No idempotency key.** There is currently no dedup mechanism on batch
> creation — if your request times out or your connection drops after the
> voice engine already accepted it, blindly retrying `POST /v1/batches` will
> create a **second real batch** (and place a second round of real calls).
> Before retrying an ambiguous failure, check
> `GET /v1/batches/by-agent/{agent_id}` for a batch you already recognize, or
> maintain your own client-side ledger of submitted requests.

### 8.2 `POST /v1/batches/upload` — create from a CSV file

Same effect as above, but you supply a CSV directly instead of a JSON list —
useful for very large recipient lists. `multipart/form-data`:

```bash
curl -X POST https://<host>/v1/batches/upload \
  -H "X-API-Key: $KEY" \
  -F "agent_id=37768781-4fc4-4df2-a80f-a847b6dad8d2" \
  -F "file=@recipients.csv" \
  -F 'from_phone_numbers=["+91XXXXXXXXXX"]'
```

**Form fields** (`multipart/form-data`):

| Field | Required | Notes |
|---|---|---|
| `agent_id` | yes | Must be enabled for your client |
| `file` | yes | CSV file, UTF-8, comma-delimited, header row required |
| `from_phone_numbers` | no | JSON array string, e.g. `["+91..."]` |
| `webhook_url` | no | Same replaces-turing behavior described in §8.1 — leave unset unless intentional |

CSV requirements:
- A header row with a `contact_number` column (E.164 format).
- Any other column becomes a prompt variable, matched by column name.

**Response** — same shape as §8.1 (`201`), but **`warnings` is always
empty** here:

```json
{ "batch_id": "b_def456", "state": "created", "warnings": [] }
```

**Note:** the upload path does **not** run the required-variable validation
that `POST /v1/batches` does — turing can't inspect CSV rows the same way
(so a missing required variable fails silently on the voice engine's side
instead of a `422` up front). Prefer the JSON endpoint when you want the
pre-flight check; use upload for bulk lists you've already validated on your
side.

### 8.3 `POST /v1/batches/{batch_id}/schedule`

Delay a created batch to a future time instead of running immediately.

```bash
curl -X POST https://<host>/v1/batches/b_abc123/schedule \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"scheduled_at": "2026-07-20T09:30:00+00:00", "bypass_call_guardrails": false}'
```

| Field | Required | Notes |
|---|---|---|
| `scheduled_at` | yes | ISO 8601, e.g. `2026-07-20T09:30:00+00:00`. A bare `Z` suffix is fine too — turing normalizes it to `+00:00` for you before forwarding upstream. Must be **at least 2 minutes in the future**; rounded up to the next 10-minute mark by the voice engine. |
| `bypass_call_guardrails` | no | Skips the voice engine's calling-time guardrail checks (e.g. do-not-call windows). Leave unset/`false` unless you know you need this. |

```json
{ "message": "Batch scheduled.", "state": "scheduled" }
```

### 8.4 `GET /v1/batches/{batch_id}` — status

```bash
curl https://<host>/v1/batches/b_abc123 -H "X-API-Key: $KEY"
```

```json
{
  "batch_id": "b_abc123",
  "status": "in_progress",
  "agent_id": "37768781-4fc4-4df2-a80f-a847b6dad8d2",
  "scheduled_at": null,
  "from_phone_numbers": ["+91XXXXXXXXXX"],
  "valid_contacts": 120,
  "total_contacts": 125,
  "created_at": "2026-07-12T18:44:54.410785Z",
  "updated_at": "2026-07-12T19:01:02.100000Z"
}
```

`status` is refreshed live from the voice engine while the batch is active;
once terminal (`completed`/`stopped`/`failed`/`deleted`) it's served straight
from turing's own record.

### 8.5 `GET /v1/batches/by-agent/{agent_id}` — list your batches for an agent

```bash
curl https://<host>/v1/batches/by-agent/37768781... -H "X-API-Key: $KEY"
```

```json
[
  {
    "batch_id": "b_abc123",
    "status": "completed",
    "agent_id": "37768781-4fc4-4df2-a80f-a847b6dad8d2",
    "scheduled_at": null,
    "from_phone_numbers": ["+91XXXXXXXXXX"],
    "valid_contacts": 120,
    "total_contacts": 125,
    "created_at": "2026-07-12T18:44:54.410785Z",
    "updated_at": "2026-07-12T20:10:00.000000Z"
  }
]
```

Returns only **your** batches for that agent, newest first — this reads
turing's own database, not the upstream engine, so it's fast and correctly
scoped even though the upstream account is shared across all clients. Note
this list is not paginated — for accounts with a very large batch history,
expect a proportionally large response.

### 8.6 `GET /v1/batches/{batch_id}/executions` — per-call results

```bash
curl https://<host>/v1/batches/b_abc123/executions -H "X-API-Key: $KEY"
```

```json
[
  {
    "id": "exec_xyz",
    "agent_id": "37768781-4fc4-4df2-a80f-a847b6dad8d2",
    "status": "completed",
    "conversation_duration": 42.5,
    "total_cost": 0.15,
    "transcript": "...",
    "extracted_data": {"outcome": "confirmed"},
    "telephony_data": {"to_number": "+919876543210", "recording_url": "..."}
  }
]
```

This is also your **reconcile path** — call it any time to pull the latest
state for every call in the batch, independent of whether the webhook (§10)
fired successfully. Safe to poll periodically (e.g. every few minutes while
a batch is active) as a backstop.

### 8.7 `GET /v1/batches/{batch_id}/metrics` — aggregate stats

```bash
curl https://<host>/v1/batches/b_abc123/metrics -H "X-API-Key: $KEY"
```

```json
{
  "batch_id": "1234...-uuid",
  "voice_batch_id": "b_abc123",
  "status": "completed",
  "total_recipients": 125,
  "calls_tracked": 125,
  "by_status": {"completed": 100, "no-answer": 20, "failed": 5},
  "completed": 100,
  "terminal": 125,
  "success_rate": 0.8,
  "total_cost": 18.75,
  "avg_duration_seconds": 38.2
}
```

Computed from turing's own stored call records, not a live upstream call —
cheap to call frequently.

### 8.8 `POST /v1/batches/{batch_id}/stop`

Halts a queued or running batch.

```bash
curl -X POST https://<host>/v1/batches/b_abc123/stop -H "X-API-Key: $KEY"
```

### 8.9 `DELETE /v1/batches/{batch_id}`

Removes the batch on the voice engine. turing retains your historical record
(status, metrics, call history) regardless.

```bash
curl -X DELETE https://<host>/v1/batches/b_abc123 -H "X-API-Key: $KEY"
```

---

## 9. Endpoint summary

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/register` | Register your client (no key needed) |
| GET | `/v1/agents` | List agents enabled for you |
| GET | `/v1/agents/{agent_id}/variables` | Required/optional prompt variables |
| GET | `/v1/phone-numbers` | Available caller IDs + your default |
| POST | `/v1/batches` | Create a batch from JSON recipients |
| POST | `/v1/batches/upload` | Create a batch from a CSV file |
| POST | `/v1/batches/{batch_id}/schedule` | Schedule a created batch |
| GET | `/v1/batches/{batch_id}` | Batch status |
| GET | `/v1/batches/by-agent/{agent_id}` | Your batches for an agent |
| GET | `/v1/batches/{batch_id}/executions` | Per-call results (also reconcile) |
| GET | `/v1/batches/{batch_id}/metrics` | Aggregate campaign stats |
| POST | `/v1/batches/{batch_id}/stop` | Stop a running batch |
| DELETE | `/v1/batches/{batch_id}` | Delete a batch |

---

## 10. Receiving outcomes — your webhook endpoint

Ask turing's operator to set your `webhook_url` (and a `webhook_secret`) on
your client config. Once set, turing will `POST` a lean outcome to that URL
every time a call in one of your batches reaches a new state — you don't
need to poll (though §8.6 is there as a backstop).

### Payload

```
POST <your webhook_url>
Content-Type: application/json
X-Webhook-Signature: sha256=<hex hmac>
```

```json
{
  "turing_call_id": "5b0e9390-4d07-43b7-aba8-cfcf1099fe11",
  "turing_batch_id": "b_abc123",
  "voice_call_id": "exec_xyz",
  "patient_uhid": "test-patient-1",
  "contact_number": "+919876543210",
  "agent_id": "37768781-4fc4-4df2-a80f-a847b6dad8d2",
  "status": "completed",
  "disposition": null,
  "recording_url": "https://.../recording.mp3",
  "cost": 0.15,
  "duration": 42.5,
  "hangup_reason": "user_hangup"
}
```

`turing_batch_id` is the same `batch_id` you got from `POST /v1/batches` —
use it to correlate the callback with your campaign.

### Verifying the signature

The signature is an HMAC-SHA256 over the **exact raw request body**, hex
digested, prefixed `sha256=`, keyed with the `webhook_secret` you were given.
**Verify it before trusting the payload.**

**Python:**

```python
import hashlib, hmac

def verify(raw_body: bytes, signature_header: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)
```

**Node.js:**

```javascript
const crypto = require("crypto");

function verify(rawBody, signatureHeader, secret) {
  const expected = "sha256=" + crypto.createHmac("sha256", secret).update(rawBody).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signatureHeader));
}
```

Important: hash the **raw bytes** of the request body, not a re-serialized
version of the parsed JSON (key ordering/whitespace differences will break
the comparison).

### Reliability

- Delivery is best-effort with **no retry at all** — a single attempt per
  event. If your endpoint is down, slow, or errors, turing logs it and moves
  on; that outcome update is not redelivered. Use §8.6
  (`GET .../executions`) as a periodic reconcile poll so a missed webhook
  never means missed data — treat the webhook as a low-latency notification,
  not your source of truth.
- Respond `2xx` quickly; do slow processing (e.g. writing to your own DB)
  after acknowledging, not before.
- Your endpoint should be idempotent on `voice_call_id` — the same execution
  may be delivered more than once as its status progresses (e.g.
  `ongoing` → `completed`).

---

## 11. Worked end-to-end flow

```bash
KEY="tk_your_api_key"
HOST="https://<host>"

# 1. Discover your enabled agents
curl $HOST/v1/agents -H "X-API-Key: $KEY"

# 2. Check what an agent needs per recipient
curl $HOST/v1/agents/<agent_id>/variables -H "X-API-Key: $KEY"

# 3. Place a batch
curl -X POST $HOST/v1/batches -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"agent_id":"<agent_id>","recipients":[{"contact_number":"+91...","<var>":"..."}]}'

# 4. Poll status (or just wait for your webhook)
curl $HOST/v1/batches/<batch_id> -H "X-API-Key: $KEY"

# 5. Pull per-call results / reconcile
curl $HOST/v1/batches/<batch_id>/executions -H "X-API-Key: $KEY"

# 6. Get aggregate metrics once done
curl $HOST/v1/batches/<batch_id>/metrics -H "X-API-Key: $KEY"
```

Meanwhile, your webhook endpoint receives a signed outcome POST for each call
as it completes — no polling required for real-time updates, but §4 and §8.6
are there if you need them.
