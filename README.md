# turing_service

A standardized, callable **micro-service that places outbound voice calls via
the [Bolna](https://www.bolna.ai) voice-AI API**. Any platform can invoke it
over an authenticated HTTP API; turing owns the Bolna integration, validates
requests against each agent's variable contract, persists every call/batch in
its own database, and (optionally) forwards call outcomes to a consumer's
webhook.

- **Stack:** FastAPI · SQLAlchemy (async) + Alembic · PostgreSQL · httpx
- **Default port:** `8005`
- **Auth:** shared `X-API-Key` header on all business endpoints
- **API version prefix:** `/v1`

Also hosted in this repo (operationally independent of the voice service):
**SQL Builder Agent** (`app/sql_agent/`, in development) — a natural-language-to-SQL
agent targeting Kalaam's Postgres. See
[docs/SQL Builder Agent - Implementation.md](docs/SQL%20Builder%20Agent%20-%20Implementation.md)
for the plan and [docs/kalaam-db-schema.md](docs/kalaam-db-schema.md) for the full
introspected schema of the target DB (exactly what gets fed to its metadata/embeddings).

---

## 1. What it does

- **Single calls** — place one outbound call now or scheduled (`POST /v1/calls`).
- **Batch campaigns** — create a batch from a JSON recipient list (turing builds
  the CSV Bolna needs), schedule it, monitor executions, stop/delete.
- **Per-agent variable validation** — reads an agent's Bolna prompt (read-only)
  to discover its `{variables}` and rejects calls/batches missing a required
  one (`422`), so you never place a call with an unfilled prompt.
- **Agent & phone-number discovery** — list Bolna agents, an agent's variable
  contract, and owned caller-IDs (for building UI dropdowns).
- **Own datastore** — batches, calls (status/transcript/recording/cost), and
  request logs live in turing's Postgres, independent of Bolna.
- **Outcome pipeline** — receives Bolna execution webhooks, persists them, and
  forwards a lean outcome to a configured consumer webhook (HMAC-signed).
- **Standard API conventions** — `/v1` prefix, `X-Request-ID` on every
  response, one consistent JSON error envelope.

---

## 2. Requirements

- Python 3.12+
- PostgreSQL 17 (provided via Docker Compose below)
- A **Bolna API key** (Bearer token from your Bolna account)
- Docker + Docker Compose (for the bundled Postgres)

---

## 3. Setup

```bash
cd turing_service

# 1. Python env + deps
python -m venv .venv
.venv\Scripts\activate            # Windows (bash: source .venv/Scripts/activate)
pip install -r requirements.txt

# 2. Environment
cp .env.example .env              # then edit — at minimum set BOLNA_API_KEY
                                  # and change TURING_API_KEYS for anything real

# 3. Database (dedicated Postgres on host port 5433)
docker compose up -d postgres

# 4. Apply the schema
alembic upgrade head

# 5. Run the service
uvicorn app.main:app --host 0.0.0.0 --port 8005 --reload
```

- Interactive API docs (Swagger): **http://localhost:8005/docs**
- Liveness: **http://localhost:8005/health** · Readiness (checks DB):
  **http://localhost:8005/health/ready**

> The bundled Postgres uses host port **5433** to avoid colliding with other
> local Postgres instances. Change it with `TURING_PG_PORT`.

---

## 4. Configuration (environment variables)

Loaded from environment / `.env` (see `app/config.py`). Unknown vars are ignored.

| Variable | Default | Purpose |
|---|---|---|
| `BOLNA_API_KEY` | — (**required**) | Bolna Bearer token turing calls Bolna with |
| `BOLNA_BASE_URL` | `https://api.bolna.ai` | Bolna API base URL |
| `BOLNA_TIMEOUT_SECONDS` | `30` | httpx timeout for Bolna calls |
| `BOLNA_DEFAULT_FROM_NUMBER` | _(unset)_ | Default caller-ID (E.164) when a request omits one |
| `DATABASE_URL` | `postgresql+asyncpg://turing:turing@localhost:5433/turing_db` | turing's own Postgres (async) |
| `TURING_API_KEYS` | `dev-turing-key` | **Comma-separated** accepted `X-API-Key` values. **Change in production.** |
| `TURING_PUBLIC_URL` | _(unset)_ | Publicly reachable base URL of turing; used as the `webhook_url` handed to Bolna (`…/webhooks/bolna`). If unset, no webhook is attached (see §10). |
| `KALAAM_WEBHOOK_URL` | _(unset)_ | Consumer callback URL turing forwards lean outcomes to. If unset, forwarding is disabled. |
| `KALAAM_WEBHOOK_SECRET` | _(unset)_ | HMAC-SHA256 secret turing signs forwarded outcomes with (`X-Webhook-Signature`). |
| `BOLNA_WEBHOOK_ALLOWED_IPS` | _(empty)_ | Comma-separated source IPs allowed to call `/webhooks/bolna` (Bolna publishes `13.203.39.153`). Empty disables the check (dev). |
| `AGENT_VARIABLES_FILE` | `agent_variables.json` | Optional per-agent optional-variable overrides (see §9) |
| `VALIDATE_AGENT_VARIABLES` | `true` | Reject calls/batches missing a required variable |
| `PORT` / `HOST` / `LOG_LEVEL` / `ENVIRONMENT` | `8005` / `0.0.0.0` / `INFO` / `development` | Service basics |
| `TURING_PG_USER` / `TURING_PG_PASSWORD` / `TURING_PG_DB` / `TURING_PG_PORT` | `turing` / `turing` / `turing_db` / `5433` | Compose Postgres settings |

> Note: the `KALAAM_*` names are generic "consumer webhook" settings (named for
> the first consumer). Any platform that wants outcomes pushed to it sets these
> to its own callback URL + secret.

---

## 5. Authentication

All business endpoints under `/v1/*` require a shared secret in the
**`X-API-Key`** header. Accepted keys come from `TURING_API_KEYS`
(comma-separated — supports rotating/multiple keys).

```bash
curl -H "X-API-Key: dev-turing-key" http://localhost:8005/v1/agents
```

- Missing/invalid key → `401` with the standard error envelope.
- `/health`, `/health/ready` are **open** (no key).
- `/webhooks/bolna` is **not** key-protected; it's guarded by the
  `BOLNA_WEBHOOK_ALLOWED_IPS` source-IP allowlist instead.

---

## 6. API conventions

- **Base URL:** `http://<host>:8005`
- **Versioning:** business endpoints under `/v1`.
- **Request ID:** every response carries `X-Request-ID` (also echoed in error
  bodies) for cross-service tracing.
- **Error envelope (always):**
  ```json
  { "error": "<code>", "message": "<human-readable>", "detail": <any|null>, "request_id": "<id>" }
  ```
  Upstream Bolna failures pass through Bolna's status code with
  `error: "bolna_error"`; transport failures → `502`. Variable-validation
  failures are `422` and keep their structured `detail`.
- **Content type:** JSON in/out (turing handles the multipart encoding Bolna
  requires internally).

---

## 7. Endpoints

### Health (open)
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness — service name, version, environment |
| GET | `/health/ready` | Readiness — confirms the turing DB is reachable |

### Bolna status
| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/bolna/status` | Probe Bolna connectivity + credential validity (returns account info) |

### Agents
| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/agents` | List all Bolna agents on the account |
| GET | `/v1/agents/{agent_id}/variables` | The agent's required/optional prompt variables + system-injected list |

### Phone numbers
| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/phone-numbers` | Owned caller-IDs + the configured default |

### Calls (single)
| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/calls` | Place one call now, or schedule (`scheduled_at`) |
| GET | `/v1/calls/{execution_id}` | Status / transcript / outcome (turing DB, refreshed from Bolna while live) |
| POST | `/v1/calls/{execution_id}/stop` | Cancel a queued/scheduled call |

### Batches (campaigns)
| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/batches` | Create a batch from a JSON recipient list (validates vars, persists) |
| POST | `/v1/batches/upload` | Create a batch from a raw CSV upload (multipart) |
| POST | `/v1/batches/{batch_id}/schedule` | Schedule a created batch to run |
| GET | `/v1/batches/by-agent/{agent_id}` | List an agent's batches (live from Bolna) |
| GET | `/v1/batches/{batch_id}` | Batch status (turing record, refreshed from Bolna) |
| GET | `/v1/batches/{batch_id}/executions` | Per-call executions in the batch |
| GET | `/v1/batches/{batch_id}/metrics` | Counts / cost / success-rate from turing's records |
| POST | `/v1/batches/{batch_id}/stop` | Halt a running batch |
| DELETE | `/v1/batches/{batch_id}` | Delete a batch |

### Webhook (Bolna → turing; IP-allowlist)
| Method | Path | Purpose |
|---|---|---|
| POST | `/webhooks/bolna` | Receives Bolna execution pushes; persists + forwards lean outcome |

---

## 8. Usage examples

All examples assume `KEY=dev-turing-key` and base `http://localhost:8005`.

### Probe Bolna
```bash
curl -H "X-API-Key: $KEY" http://localhost:8005/v1/bolna/status
```

### Discover an agent's variables
```bash
curl -H "X-API-Key: $KEY" http://localhost:8005/v1/agents
curl -H "X-API-Key: $KEY" http://localhost:8005/v1/agents/<agent_id>/variables
# → { "agent_id": "...", "required": ["patient_name", ...],
#     "optional": [], "system_injected": ["current_date", "to_number", ...] }
```

### Place a single call (now)
```bash
curl -X POST http://localhost:8005/v1/calls \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{
    "agent_id": "<agent_id>",
    "recipient_phone_number": "+919876543210",
    "user_data": { "patient_name": "Asha", "doctors_name": "Dr. Rao" },
    "retry_config": { "enabled": true, "max_retries": 2,
                      "retry_on_statuses": ["no-answer","busy"] }
  }'
# → { "status": "queued", "execution_id": "...", "warnings": [] }
```
Schedule instead of calling now by adding
`"scheduled_at": "2026-07-20T18:30:00+00:00"` (ISO-8601 **numeric offset** — the
`Z` suffix is rejected by Bolna; turing normalizes it if present).

### Track a call
```bash
curl -H "X-API-Key: $KEY" http://localhost:8005/v1/calls/<execution_id>
```

### Create + schedule a campaign
```bash
# 1. Create (returns batch_id; batch is a draft until scheduled)
curl -X POST http://localhost:8005/v1/batches \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{
    "agent_id": "<agent_id>",
    "from_phone_numbers": ["+918035739222"],
    "retry_config": { "enabled": true, "max_retries": 1 },
    "recipients": [
      { "contact_number": "+9199...", "patient_name": "Asha", "doctors_name": "Dr. Rao" },
      { "contact_number": "+9198...", "patient_name": "Ravi", "doctors_name": "Dr. Rao" }
    ]
  }'
# → { "batch_id": "<bolna_batch_id>", "state": "created", "warnings": [] }

# 2. Schedule it (Bolna runs it at this time)
curl -X POST http://localhost:8005/v1/batches/<batch_id>/schedule \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{ "scheduled_at": "2026-07-20T18:30:00+00:00" }'
# → { "message": "success", "state": "scheduled" }

# 3. Monitor
curl -H "X-API-Key: $KEY" http://localhost:8005/v1/batches/<batch_id>
curl -H "X-API-Key: $KEY" http://localhost:8005/v1/batches/<batch_id>/executions
curl -H "X-API-Key: $KEY" http://localhost:8005/v1/batches/<batch_id>/metrics
```

**Recipient contract:** each recipient object needs `contact_number` (E.164);
every other key becomes a prompt variable for that call. turing validates the
variables against the agent's contract (§9) before creating the batch.

---

## 9. Variable validation (per agent)

turing reads the selected agent's Bolna prompt (read-only) and extracts its
`{placeholder}` variables. On a call/batch it checks the supplied variables:

- **Missing a required variable →** `422` with a structured `detail`
  (`{error: "missing_required_variables", required: [...], rows: [...]}`).
- **Extra/unused variable →** allowed, returned as a non-blocking `warning`.
- **System variables** (`current_date`, `to_number`, `execution_id`, …) are
  auto-injected by Bolna and must not be supplied.

Every prompt variable is **required by default**. To mark some optional per
agent, add an entry to the file named by `AGENT_VARIABLES_FILE`
(`agent_variables.json`), e.g.:
```json
{ "<agent_id>": { "optional": ["nickname"] } }
```
Set `VALIDATE_AGENT_VARIABLES=false` to disable validation entirely.

> Variable names are **case-sensitive** and must match the agent's prompt
> placeholders exactly (e.g. `Follow_Up_Date` vs `follow_up_date`). Use
> `GET /v1/agents/{id}/variables` as the source of truth.

---

## 10. Scheduling & outcome flow

**Scheduling (batches):** Bolna requires `scheduled_at` **≥ 2 minutes** in the
future and **rounds up to the next 10-minute mark**. Bolna itself executes the
batch at that time; turing does not need to trigger it. (turing sends the
schedule as multipart/form-data, as Bolna requires.)

**Outcomes:** when a call finishes, Bolna POSTs the execution to
`POST /webhooks/bolna`. turing persists it (status, transcript, recording, cost)
and — if `KALAAM_WEBHOOK_URL` is set — forwards a **lean outcome** to that URL,
signed with `X-Webhook-Signature: sha256=<hmac>` (secret `KALAAM_WEBHOOK_SECRET`).

> **Local-dev caveat:** Bolna cannot reach `localhost`. For real-time webhooks,
> set `TURING_PUBLIC_URL` to a publicly reachable URL (e.g. an ngrok tunnel) so
> turing attaches a reachable `webhook_url` to Bolna batches/calls. Without a
> public URL, consumers should **poll** `GET /v1/calls/{id}` /
> `GET /v1/batches/{id}/executions` to reconcile outcomes.

Simulate a webhook locally (no real call):
```bash
curl -X POST http://localhost:8005/webhooks/bolna -H "Content-Type: application/json" \
  -d '{ "id": "test-exec-1", "status": "completed", "total_cost": 3.2,
        "conversation_duration": 33,
        "telephony_data": { "to_number": "+9199...", "recording_url": "https://..." },
        "context_details": { "recipient_data": { "patient_uhid": "UH1" } },
        "batch_run_details": { "batch_id": "<bolna_batch_id>" } }'
```

---

## 11. Data model (turing's Postgres)

Three tables, all UUID primary keys, all carrying `created_at` / `updated_at`
(timezone-aware, auto-managed). `batches` and `calls` form the campaign→call
hierarchy; `request_logs` stands alone as an audit trail.

```
 ┌──────────────────────────────────────────────┐
 │ batches                    (one per campaign) │
 ├──────────────────────────────────────────────┤
 │ PK  id                 uuid                    │
 │     client             varchar(64)   caller    │
 │     agent_id           varchar(64)   NN        │
 │     from_number        varchar(32)   caller-ID │
 │     mode               varchar(16)   NN 'batch'│
 │     retry_config       jsonb                   │
 │ U,IX bolna_batch_id    varchar(64)  ← Bolna id │
 │     status             varchar(32)   NN        │
 │     total_count        integer       NN        │
 │     valid_count        integer                 │
 │     scheduled_at       varchar(64)             │
 │     recipients_snapshot jsonb                  │
 │     created_at / updated_at  timestamptz  NN   │
 └───────────────┬──────────────────────────────┘
                 │ 1
                 │            batches.id  =  calls.batch_id
                 │ N          (ON DELETE: none — calls keep the fk)
 ┌───────────────┴──────────────────────────────┐
 │ calls              (one per Bolna execution:  │
 │                     single sends AND members) │
 ├──────────────────────────────────────────────┤
 │ PK   id                uuid                    │
 │ FK,IX batch_id         uuid  → batches.id  (nullable: single sends have none) │
 │      client            varchar(64)             │
 │      agent_id          varchar(64)   NN        │
 │ IX   contact_number    varchar(32)             │
 │ IX   patient_ref       varchar(128)  consumer's patient key (e.g. uhid) │
 │ U,IX bolna_execution_id varchar(64)  ← idempotency key │
 │      status            varchar(32)   NN        │
 │      transcript        text                    │
 │      recording_url     text                    │
 │      extracted_data    jsonb                   │
 │      cost              double precision         │
 │      duration          double precision         │
 │      hangup_reason     varchar(128)            │
 │      retry_count       integer                 │
 │      raw_payload       jsonb   full Bolna push │
 │      created_at / updated_at  timestamptz  NN  │
 └──────────────────────────────────────────────┘

 ┌──────────────────────────────────────────────┐
 │ request_logs        (audit — no relationships)│
 ├──────────────────────────────────────────────┤
 │ PK   id             uuid                       │
 │ IX   request_id     varchar(36)   NN  X-Request-ID │
 │      client         varchar(64)       key-XXXXXX   │
 │      method         varchar(8)    NN               │
 │      endpoint       varchar(256)  NN               │
 │      status_code    integer       NN               │
 │      latency_ms     double precision NN            │
 │      created_at / updated_at  timestamptz  NN      │
 └──────────────────────────────────────────────┘

 Legend:  PK = primary key   FK = foreign key   U = unique
          IX = indexed       NN = NOT NULL
```

**How the tables are used**

- **`batches`** — one row per campaign, created 1:1 with a Bolna batch. `bolna_batch_id`
  is the unique handle turing looks a batch up by; `status` tracks the lifecycle
  (`created → scheduled → running → completed / stopped / failed / deleted`);
  `recipients_snapshot` keeps the exact JSON that was submitted.
- **`calls`** — one row per outbound call. A **single send** has `batch_id = NULL`;
  a **campaign member** points back to its `batches.id`. `bolna_execution_id` is the
  **idempotency key**: outcome upserts (webhook *and* reconcile poll) key on it, so
  repeated deliveries for the same execution re-write the same row rather than
  duplicating. `raw_payload` stores the full Bolna push; `transcript` / `recording_url`
  / `cost` / `duration` are the extracted outcome fields.
- **`request_logs`** — written by the request middleware for every business call:
  the `X-Request-ID`, the non-secret caller label (`client` = `key-XXXXXX`), method,
  endpoint, resulting status, and latency. No FK to the other tables — pure audit.

**Consumer split:** turing is the source of truth for the *full* record (transcript,
raw payload, cost). A consumer like Kalaam stores only a **lean outcome** keyed by
`bolna_execution_id` + `patient_ref`, and calls back into turing for detail.

---

## 12. Project layout

```
app/
├── main.py            # app factory, router registration, middleware, error handlers
├── config.py          # settings (env / .env)
├── auth.py            # X-API-Key dependency
├── middleware.py      # X-Request-ID + request logging
├── errors.py          # standard error envelope + handlers
├── core/
│   ├── bolna_client.py  # async httpx client for the Bolna API
│   ├── variables.py     # prompt-variable extraction + validation
│   └── csv_utils.py     # JSON recipients → Bolna CSV
├── routers/           # health, bolna, agents, phone_numbers, calls, batches, webhooks
├── schemas/           # pydantic request/response models
├── services/          # store (DB persistence), variables, kalaam_notifier (webhook forward)
└── db/
    ├── models.py        # SQLAlchemy models (batches, calls, request_logs)
    └── session.py       # async engine/session
alembic/               # migrations (0001_initial)
docker-compose.yml     # dedicated Postgres (host :5433)
frontend/              # optional dev console (Next.js) — not required to run the service
```

---

## 13. Operational notes

- **Ports in this workspace:** turing app `8005`, turing Postgres `5433`
  (distinct from other local Postgres on `5432` / `5434`).
- **Reset DB:** `docker compose down -v` (drops the volume) then
  `docker compose up -d postgres && alembic upgrade head`.
- **Production checklist:** set a strong `TURING_API_KEYS`; set
  `BOLNA_WEBHOOK_ALLOWED_IPS=13.203.39.153`; set `TURING_PUBLIC_URL` +
  `KALAAM_WEBHOOK_URL` / `KALAAM_WEBHOOK_SECRET` for the outcome pipeline; run
  behind TLS.
</content>
