# SQL Builder Agent — implementation notes

Working log for the multi-agent build of `app/sql_agent/` per
[docs/SQL Builder Agent - Implementation.md](docs/SQL%20Builder%20Agent%20-%20Implementation.md).
Topology: 2 builders + 1 critic per round; nothing merges on a REVISE verdict.

## Round log

### Round 1 — Phase 1 foundations ✅ (double APPROVE)
- Builder A: deps (§9) + `config.py` + `control_db/` (9 models, session, bootstrap). Verified live:
  `sql_agent_db` created on turing-postgres, vector 0.8.5, all 9 tables + spec'd constraints, idempotent re-run.
- Builder B: `target_db.py` (read-only engine, forced `default_transaction_read_only=on` + statement_timeout)
  + `ingestion/introspect.py`. Live dry run reconciled with schema doc: 68 tables / 1108 cols (=1112 minus
  the excluded view's 4) / 155 FKs.
- Critic: APPROVE×2. Adversarially exercised bootstrap fail-closed guards (turing_db refusal, bad identifier,
  wrong embedding dim) — all held. 3 MINORs, resolved:
  1. requirements floors raised to the tested 1.x majors (applied by orchestrator).
  2. target_db reads os.environ only — Phase 3 entrypoint MUST load_dotenv at startup (noted below).
  3. kalaam.yaml provenance "unaudited" — false alarm: authored+reviewed in the enrichment rounds
     (9 drafts, 8 agent reviews + 1 orchestrator inline review, 5 repairs, live value re-verification).

## Phase 3 reminders
- Graph/router entrypoint must load .env into process env (load_dotenv) before target_db use.
- Installed line is langchain 1.x / langgraph 1.x — use 1.x interrupt/checkpoint APIs, not 0.2 tutorial patterns.
- Builder A's model-tier defaults: generate=claude-sonnet-4-5, rest=claude-haiku-4-5 — placeholders, env-overridable.
- create_all won't ALTER: model changes after data exists need drop/recreate or the Alembic upgrade.
- Retrieval must filter `embedding IS NOT NULL` and join through `is_active=true`.

## Environment facts (local dev)
- Control plane: turing-postgres container (pgvector/pgvector:pg17), localhost:5433 — new database `sql_agent_db` alongside `turing_db`
- Target: kalam-postgres, localhost:5435, database `continental-pilot-local`, role `sql_agent_readonly` (SELECT-only, 10s timeout, read-only transactions — verified at DB level)
- Enrichment source of truth: `app/sql_agent/workspaces/kalaam.yaml` (68 tables, reviewed)
- API keys: NOT yet in .env — required before Phase 2 embedding/auto-describe

## Deviations
- Enrichment YAML drafted pre-build (plan schedules auto_describe at Phase 2 runtime) — deliberate sequencing improvement, richer first ingestion.
- 2026-07-27 generate-only implementation follows `docs/SQL Builder Agent - Implementation.md`: plain async service functions, deterministic sqlglot guard, committed allowlist snapshot, model-agnostic LangChain factory, `/v1/sql-agent/query`, and offline guard/eval harness. Legacy control-plane/vector modules remain present but are not imported by the new build path.

## 2026-07-27 verification
- `ruff check .` passed.
- `pytest tests/sql_agent` passed: 34 tests.
- `pytest tests/sql_agent/test_sql_guard.py` passed: 13 tests.
- `mypy .` passed after aligning `pyproject.toml` with the documented Python 3.12 baseline.
- `mypy --python-version 3.12 .` passed.
- `mypy --python-version 3.12 app/sql_agent app/routers/sql_agent.py tests/sql_agent/test_sql_guard.py` passed.
- `load_catalog("kalaam").summary()` reports 68 tables and 1108 columns.
- `app.main.create_app()` includes `/v1/sql-agent/query` after installing `requirements.txt`.
- Default model factory initializes `ChatGoogleGenerativeAI` with a placeholder `GOOGLE_API_KEY` without making a provider call.

## Open questions
- Production Postgres: Cloud SQL vs self-hosted container on GCE VM (affects how pgvector is enabled in prod; does not block local build).
- Model-tier choices per node (§9 placeholders) — decide before Phase 3 graph work.
