# Prod Secrets & Backup — Pending Hardening

**Status: pending.** Not blockers for the initial prod push — operational hardening to do afterwards.

## Real "lose clients" risks — address first

1. **Postgres backups.** Clients live only in the DB (`clients`, `client_config`, `api_keys`). This is the *only* true client-loss scenario. Set up automated backups **and a tested restore**.
2. **`ENCRYPTION_KEY` must be stable + backed up.** It encrypts per-client LLM keys (`client_config.analysis_llm_api_key_enc`). Pick it once, store it safely, and **never regenerate it in prod** — regenerating makes those keys undecryptable and clients must re-enter their LLM key. (Only that field is affected; the clients themselves survive.)
3. **Back up the DB before running migrations.** `0015` drops `call_analysis.outcome` — irreversible loss of the pre-rollout coarse classifications. Snapshot first.

## Safe to rotate anytime (redeploy, no data loss)

4. **`OPERATOR_PASSWORD` / `OPERATOR_SESSION_SECRET`** — console login only; the session cookie holds no client data. Rotating the secret invalidates existing login sessions. No client impact.
5. **`ADMIN_API_KEY`** — console↔backend credential (`X-Admin-Key`). Rotate on both backend and frontend, then redeploy. No data loss.

## Client credentials

6. **Client `X-API-Key`s are stored hashed** — non-recoverable by design. If a client loses theirs, issue a new key; the original cannot be retrieved. Document/automate the re-issue flow.

## Notes
- `.env` / `.env.prod` are gitignored — local/dev keys never reach prod. Use strong, distinct values in `.env.prod` (don't carry over the short dev `ADMIN_API_KEY`).
- Two webhook directions: **inbound** (Bolna → turing) via `TURING_PUBLIC_URL`; **outbound** (turing → client) is per-client `webhook_url` + `webhook_secret` in `client_config`.
