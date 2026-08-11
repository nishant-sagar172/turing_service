Plan: Make turing_service multi-tenant (per-client batches, calls, logs, analytics)
Context
turing is currently single-tenant: one shared X-API-Key (defaulting to dev-turing-key) authenticates any caller, every caller sees all Bolna agents, and the batches / calls / request_logs tables carry only a cosmetic client label (key-xxxxxx) that nothing filters on. It works because there is exactly one consumer.

The goal is to serve multiple independent clients from one turing instance and one Bolna account, where each client:

registers and is issued a client_id (uuid) + an API key;
can place calls and batches, and later see logs and analytics, that are strictly its own — no client can see another client's records;
sees, on the agent-list endpoint, only the Bolna agents configured/enabled for it (e.g. of 30 Bolna agents, client 1 has {1,2,4,30} enabled → only those are returned), never the raw Bolna catalog;
is notified — logged in turing and surfaced to the frontend — when one of its configured agents is no longer available on Bolna (deleted / missing from the Bolna agent list). Renames or status changes are NOT drift.
End state: batches, calls, logs, (future) analytics are all partitioned by client.

Scope: turing_service repo ONLY. No Kalaam / other-repo changes in this plan. Confirmed decisions: fresh schema (wipe dev data); local synced agent catalog; row-level isolation first (field-level projection structure staged for follow-up); self-serve registration + admin approval onboarding, bootstrapped by an env-seeded ADMIN_API_KEY.

Core concepts
Tenant = client, keyed by client_id (uuid).
API key → client resolution. A key no longer grants blanket access; it resolves to exactly one client. The authenticated client_id is attached to the request and threaded into every DB read and write.
Row-level isolation. Every domain row carries client_id; every read filters by the caller's client_id; cross-tenant access returns 404 (never leak existence).
Local agent catalog + per-client enablement. turing keeps its own cached snapshot of Bolna agents and a per-client enable table; the client-facing agent list is served from these, not from a live Bolna call. A sync job refreshes the catalog and records drift that affects a client's enabled agents.
New / changed data model (fresh schema — single rewritten initial migration)
Because we wipe dev data, the cleanest path is to rewrite 0001_initial into the full multi-tenant schema (dev-only; no production backfill needed).

New tables:

clients — id (uuid PK), name (unique), slug, contact_email?, status (pending → active → suspended, or rejected), approved_at?, approved_by?, timestamps. The tenant root. Self-serve registration creates a client in pending; an admin transitions it to active (approve) or rejected.
client_api_keys — id, client_id (FK), key_hash (store a SHA-256 hash, never plaintext), key_prefix (first ~8 chars, for identification/logs), label, status (active/revoked), last_used_at, expires_at?, timestamps. Supports multiple keys + rotation per client. The client's first key is minted at approval time (plaintext shown once to the admin); keys of a non-active client never authenticate.
client_config — id, client_id (FK, unique 1:1), visible_fields (jsonb) — per-resource field allowlist structure defined now, enforcement deferred; default_from_number?; webhook_url? + webhook_secret? (per-client outcome callback — replaces today's single global KALAAM_WEBHOOK_*); settings (jsonb) (e.g. per-client validate_agent_variables override).
agent_catalog — id, bolna_agent_id (unique), agent_name, agent_status, snapshot (jsonb) (raw Bolna agent incl. prompt for variable extraction), is_present (bool), first_seen_at, last_synced_at, timestamps. turing's cached view of the Bolna account.
client_agent_config — id, client_id (FK), bolna_agent_id, enabled (bool), display_name?, variable_overrides (jsonb)? (per-client optional-variable marking — replaces the global agent_variables.json). Unique (client_id, bolna_agent_id).
agent_drift_events — id, client_id (FK, nullable for global events), bolna_agent_id, event_type (agent_removed — configured agent no longer on Bolna), detail (jsonb), acknowledged (bool), created_at. The record the frontend reads and turing logs.
Changed tables:

batches, calls, request_logs — add client_id (uuid FK → clients.id, NOT NULL, indexed); drop the old client String column. Composite indexes as needed, e.g. calls (client_id, bolna_execution_id).
(future) analytics — not built now; note the intended client_id relation so the schema is analytics-ready.
Auth evolution
Replace the static api_key_set membership check (app/auth.py, app/config.py turing_api_keys) with DB-backed key resolution: hash the presented X-API-Key, look up an active client_api_keys row whose client is active, attach to request.state.client; 401 if no match, 403 if the client is pending/suspended/rejected. Update last_used_at.
Short-TTL in-memory cache (key-hash → client_id, ~60s) to avoid a DB hit per request; the async pool already exists in app/db/session.py.
Admin guard — a single env-seeded ADMIN_API_KEY (from settings/env) protects the /v1/admin/* surface; presented via an X-Admin-Key header. This is the bootstrap — it exists before any client and is how the first registrations get approved. Rotate by changing the env value + restart.
New dependencies in app/dependencies.py: get_current_client (business routes, requires an active client) and require_admin (admin routes, checks ADMIN_API_KEY).
Endpoints
Public onboarding (open, no key — self-serve registration):

POST /v1/register — a prospective client submits name + contact_email. Creates a client in pending and returns only its client_id + a status of pending (no usable key yet). Idempotent-ish: a duplicate name returns the existing pending record rather than creating twins. Rate-limited to deter abuse.
Admin surface (/v1/admin/*, X-Admin-Key guarded):

GET /v1/admin/clients?status=pending — review the onboarding queue; GET /v1/admin/clients, GET /v1/admin/clients/{id}.
POST /v1/admin/clients/{id}/approve — transition pending → active and mint the first API key (returned plaintext once to the admin, who relays it to the client).
POST /v1/admin/clients/{id}/reject — pending → rejected.
POST /v1/admin/clients/{id}/suspend — active → suspended (keys stop authenticating immediately).
POST /v1/admin/clients/{id}/keys (issue/rotate) · DELETE …/keys/{key_id} (revoke).
PUT /v1/admin/clients/{id}/config — visible_fields, default number, webhook.
PUT /v1/admin/clients/{id}/agents — set the client's enabled Bolna agent ids (bulk).
POST /v1/admin/agents/sync — trigger a Bolna catalog sync (also scheduled).
GET /v1/admin/clients/{id}/drift — drift events for a client.
Client surface (/v1/*, client-key guarded — now tenant-scoped):

GET /v1/agents — served from agent_catalog ⋈ client_agent_config where enabled AND is_present, not a live Bolna call. Only the client's configured agents.
GET /v1/agents/{id}/variables — only if enabled for the client; contract from the cached snapshot + the client's variable_overrides.
GET /v1/phone-numbers — per-client default_from_number.
POST /v1/calls, POST /v1/batches — reject (403) if agent_id not enabled for this client; stamp client_id on the rows; forward outcomes via the client's webhook config.
All GET reads (/calls/{id}, /batches/{id}, by-agent, executions, metrics, list) — filtered by client_id; 404 if a row belongs to another client. A client sees ONLY its own call logs and records — batch listings, call lookups, executions, and metrics are all scoped to the authenticated client; another client's data is never returned and its existence is never revealed.
GET /v1/batches/by-agent/{agent_id} changes source: today it lists live from Bolna (no client notion). It must read turing's DB filtered by client_id (+ agent), so it can't leak other clients' batches.
Agent catalog sync + drift detection
New service app/services/agent_sync.py:

Sync: fetch Bolna /v2/agent/all (existing BolnaClient.list_agents) → upsert into agent_catalog; mark agents absent from the response is_present = false.
Drift: after each sync, for every enabled client_agent_config, check whether its agent is still present on Bolna. If it is now absent (deleted/unavailable, is_present = false) → write an agent_drift_events row scoped to that client and logger.warning(...) it. Renames / status changes do NOT count as drift.
Trigger: manual (POST /v1/admin/agents/sync) plus an in-process periodic task started in the FastAPI lifespan (app/main.py), interval from settings. No external scheduler — flagged for review.
Frontend: reads GET /v1/admin/clients/{id}/drift; turing logs independently.
Per-client outcome webhook
A call outcome returns over two hops: (1) inbound Bolna → turing /webhooks/bolna, then (2) outbound turing → the consumer's own callback URL (a lean, HMAC-signed summary). Hop 2 lives in app/services/kalaam_notifier.py.

Today (single-tenant): hop 2 forwards to one global KALAAM_WEBHOOK_URL signed with one global KALAAM_WEBHOOK_SECRET. Fine for one consumer, wrong for many — each client has its own system that should receive its own outcomes signed with its own secret.

Multi-tenant change (hop 2): move the destination from global config into per-client client_config.webhook_url / webhook_secret. Before forwarding, turing (a) determines which client owns the finished call, (b) loads that client's webhook URL + secret, (c) forwards + signs to it. Client A's outcomes only ever reach A's URL under A's secret.

Hop 1 needs no change — the key insight. Bolna knows nothing about clients; it just reports "execution xyz finished." turing resolves ownership from its own DB: the calls/batches row was stamped with client_id (Phase 1) when the call was placed and is keyed by bolna_execution_id / batch_id. So the inbound receiver (app/routers/webhooks.py) looks up that row → gets client_id → loads the client's config → fans out to the right client. Therefore:

one shared inbound endpoint (/webhooks/bolna) serves every client;
no per-client URL needs to be handed to Bolna, and the client is not encoded in the URL — ownership is resolved internally after the lookup.
This rides entirely on client_id being present on every calls/batches row, so it depends on Phase 1.

Rename: kalaam_notifier.py → generic outcome_notifier.py (it no longer serves only Kalaam); retire the global KALAAM_WEBHOOK_* settings in favor of the per-client client_config fields.

Files to change (turing_service only)
app/db/models.py — new tables; client_id FK on Batch/Call/RequestLog; drop client string column.
alembic/versions/0001_initial.py — rewrite to full multi-tenant schema (dev wipe + recreate).
app/config.py — add admin_api_key (env-seeded bootstrap), agent_sync_interval_minutes; retire global turing_api_keys and kalaam_webhook_* (superseded by DB config).
app/auth.py — DB-backed resolve_client + admin guard + TTL cache.
app/dependencies.py — get_current_client, require_admin.
app/main.py — mount admin router; apply client-scope dependency to /v1 business routers; start sync background task in lifespan.
app/routers/agents.py — client-scoped catalog listing + variables from snapshot/overrides.
app/routers/batches.py, app/routers/calls.py — enforce enabled-agent; stamp client_id; scope all reads; by-agent reads DB.
app/services/store.py — every read/write takes/enforces client_id; batch_metrics scoped.
app/services/variables.py, app/core/variables.py — source config from agent_catalog snapshot + client_agent_config, not live Bolna + global file.
app/services/kalaam_notifier.py → outcome_notifier.py (per-client webhook).
app/routers/webhooks.py — resolve client from row.
app/middleware.py — write client_id into request_logs.
New: app/services/agent_sync.py; app/routers/admin.py; app/schemas/clients.py, app/schemas/admin.py; extend app/schemas/agents.py.
Implementation phases (ordered; each independently verifiable)
Phase 0 — Schema & migration. New models + rewritten initial migration; wipe & recreate the dev DB.
Phase 1 — Client identity & isolation (the core end goal). clients + client_api_keys, admin key, resolve_client/get_current_client, stamp client_id on all writes, filter all reads. Outcome: batches/calls/logs strictly per-client.
Phase 2 — Registration/onboarding endpoints. Public POST /v1/register (pending); admin approve/reject/suspend; key issue/rotate/revoke; client config. Self-serve + admin approval, gated by the env ADMIN_API_KEY.
Phase 3 — Agent catalog + per-client enablement. agent_catalog, client_agent_config, sync service, client-scoped GET /v1/agents, enforce enabled-agent on call/batch.
Phase 4 — Drift detection + logging + endpoint.
Phase 5 — Per-client outcome webhook config.
Phase 6 (future) — Analytics tables + field-level projection enforcement.
Verification (no real Bolna calls)
Isolation: register clients A and B; confirm A's key cannot read B's batch (404), and each GET /v1/batches returns only its own rows.
Agent scoping: enable {1,2,4,30} for A; GET /v1/agents returns only those; POST /v1/batches with a non-enabled agent → 403.
Drift: run a catalog sync where an enabled agent is absent from the mocked Bolna response → an agent_drift_events (agent_removed) row is created + logged; the drift endpoint returns it. A rename/status change produces NO drift event.
Onboarding lifecycle: POST /v1/register creates a pending client with no usable key; an attempt to call /v1/* fails; POST /v1/admin/clients/{id}/approve activates it and returns a key that then works; suspend makes the key stop authenticating (403).
Auth: unknown key → 401; key of a non-active client → 403; admin route without X-Admin-Key → 403; variable guard still 422 (fires before Bolna).
Safety: reuse the established read-only + validation-reject testing; use a mock Bolna for the create/schedule happy path so no real batch or call is placed.
Quality gates: ruff check . and mypy . remain clean.
Decisions locked in
Onboarding — self-serve POST /v1/register (creates a pending client) → admin approves (pending → active) and the first API key is minted at approval.
Admin auth — single env-seeded ADMIN_API_KEY via X-Admin-Key header.
Open items flagged for your review
Sync scheduler — in-process periodic asyncio task (proposed) vs external trigger/cron.
Field-level projection — the visible_fields structure ships now; when to enforce column-level projection on responses.
Register abuse controls — whether POST /v1/register needs more than basic rate-limiting (e.g. email/domain verification) given it's public.