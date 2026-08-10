Ready for review
Select text to add comments on the plan
SQL Builder Agent — Implementation Plan
Context
The user wants a natural-language-to-SQL agent, modeled on Uber's QueryGPT architecture and built with LangChain/LangGraph, that lives as a code module inside turing_service but is operationally and data-wise independent of it. It will query Kalaam's Postgres database, and must be config-driven enough to onboard other target databases later purely by supplying connection info + schema + relationships + glossary + examples — no code changes.

The real end-state integration (explicitly deferred, not built now): kalaam_frontend → kalaam_backend → this SQL agent → runs the validated query against Kalaam's DB → results shown back in kalaam_frontend. Turing's own tenant/admin model is not the consumer — it's just where the code currently lives. Current priority is the agent's core accuracy: a battle-tested, ≥95%-accurate query builder — not the integration surface.

Because generated SQL will run against production data, the design leans hard into defense-in-depth (deterministic validation, DB-level read-only enforcement, fail-closed behavior, full audit logging), accuracy-hardening (semantic critique, confidence-gated multi-candidate generation, ambiguity detection, result sanity-checking), and token efficiency (column pruning, scoped retrieval, per-node model tiering, incremental re-embedding). And because a human should see what's about to be queried, the agent proposes before it executes: every question produces SQL + a plain-language explanation first, and execution against Kalaam's DB is a distinct, later step.

Research basis: Uber's QueryGPT blog (intent agent → workspace scoping → table agent → RAG over schema/examples → column pruning → few-shot SQL generation, evaluated on intent accuracy / table-overlap / execution success), LangChain's own LangGraph SQL-agent reference architecture (list-tables → get-schema → generate → check → run, retry-on-error, native human-approval interrupts), and a "six failures of text-to-SQL" analysis (deterministic node ordering, retrieve schema instead of dumping it, writer/critic self-correction loops, AST-based validation via sqlglot, clean structured output).

Decisions made with the user (do not re-litigate):

Target DB = Kalaam's Postgres, architected generically as a "workspace/datasource" concept so more targets can be onboarded via config later.
LLM = provider-agnostic via LangChain's chat-model interface; different graph nodes use different model tiers.
Embeddings/vector storage = pgvector, confirmed sufficient — this corpus (tables + glossary terms + examples: dozens to low-thousands of rows, growing slowly) is nowhere near where a dedicated vector DB's advantages (ANN indexing at millions/billions of vectors, sub-ms latency at high QPS) matter. A standalone vector DB would just be a second system to keep in sync, for no retrieval benefit at this scale.
Embeddings provider = OpenAI text-embedding-3-small (Anthropic has no embeddings API).
Storage is fully separate from turing's own tables/database — a brand-new, dedicated Postgres database owned entirely by this feature. The eventual caller is Kalaam's backend, not turing's tenants, so there's no reason to route this through turing's Client/multi-tenant model. Code lives in this repo as app/sql_agent/; its data does not touch turing's DB.
Query flow is propose-then-execute: generate SQL + explanation + validate, surface to the caller, execute only on a distinct follow-up call.
Diagrams
(Persisted here for now since plan mode restricts writes to this file; move to docs/diagrams/ once out of plan mode, per this repo's flow-builder-visualizer skill convention.)

System architecture — three DB roles:

flowchart TB
    subgraph ext["Deferred integration (not built now)"]
        KF[kalaam_frontend]
        KB[kalaam_backend]
    end

    subgraph repo["app/sql_agent/ — this repo"]
        API[Test-harness API<br/>/sql-agent/propose · /execute]
        GRAPH[LangGraph pipeline]
        ING[Ingestion pipeline]
    end

    subgraph controldb["sql_agent_db — NEW dedicated Postgres"]
        WS[(workspaces / tables / columns /<br/>relationships / glossary / examples /<br/>embeddings / query_audit / repair_log)]
    end

    subgraph kalaamdb["Kalaam's Postgres — target, read-only"]
        KDB[(business data)]
    end

    KF -. future .-> KB -. future .-> API
    API --> GRAPH
    GRAPH <--> WS
    GRAPH -- "validated SELECT only\n(read-only role)" --> KDB
    ING -- "introspect\n(read-only)" --> KDB
    ING -- "writes metadata + embeddings" --> WS
LangGraph pipeline — propose/execute split + accuracy nodes:

flowchart TD
    A[question] --> B[workspace_resolve]
    B --> C["prompt_enhance\n(glossary, dates, write-intent reject)"]
    C -->|write-intent detected| STOP1["blocked\n(fail closed)"]
    C --> D[ambiguity_check]
    D -->|ambiguous| CLARIFY[return clarifying question]
    D --> E["table_retrieve\n(hybrid: embedding + lexical)"]
    E --> F[table_select]
    F --> G[column_prune]
    G --> H[example_retrieve]
    H --> I["sql_generate\n(sql + explanation + confidence)"]
    I -->|confidence low| J["multi_candidate_generate\n+ vote"]
    I -->|confidence ok| K["sql_critic\n(semantic check)"]
    J --> K
    K -->|issue found| M[repair]
    K --> L["validate\n(sqlglot, deterministic)"]
    L -->|errors, budget left| M
    L -->|errors, budget exhausted| STOP2["audit: repair_exhausted\n(blocked)"]
    M --> L
    L -->|clean| N["explain_guard\n(EXPLAIN)"]
    N -->|fails, budget left| M
    N -->|clean| PAUSE(("⏸ interrupt\nPROPOSE boundary"))
    PAUSE --> RESP1["return sql + explanation\n+ confidence + audit_id"]
    RESP1 -. caller/human decides .-> RESUME[resume: execute]
    RESUME --> O["execute\n(read-only role, timeout, row cap)"]
    O --> P[result_sanity_check]
    P -->|looks off| FLAG[flag caveat in response]
    P --> Q["audit\n(always runs)"]
    FLAG --> Q
    STOP1 --> Q
    STOP2 --> Q
    CLARIFY --> Q
Control-plane schema (ER):

erDiagram
    WORKSPACES ||--o{ DATASOURCES : has
    WORKSPACES ||--o{ TABLES : contains
    WORKSPACES ||--o{ GLOSSARY : defines
    WORKSPACES ||--o{ EXAMPLES : curates
    WORKSPACES ||--o{ QUERY_AUDIT : logs
    TABLES ||--o{ COLUMNS : has
    TABLES ||--o{ RELATIONSHIPS : "from/to"
    QUERY_AUDIT ||--o{ REPAIR_LOG : records

    WORKSPACES {
        uuid id PK
        string name
        bool row_scoping_enabled
    }
    DATASOURCES {
        uuid id PK
        uuid workspace_id FK
        string dialect
        string connection_env_var
    }
    TABLES {
        uuid id PK
        uuid workspace_id FK
        string table_name
        string description
        bool is_reviewed
        vector embedding
    }
    COLUMNS {
        uuid id PK
        uuid table_id FK
        string column_name
        string data_type
        bool is_sensitive
    }
    RELATIONSHIPS {
        uuid id PK
        uuid from_table_id FK
        uuid to_table_id FK
        string relationship_type
    }
    GLOSSARY {
        uuid id PK
        string term
        string definition
        vector embedding
    }
    EXAMPLES {
        uuid id PK
        string question
        string sql_text
        bool is_verified
        vector embedding
    }
    QUERY_AUDIT {
        uuid id PK
        string question
        string generated_sql
        string status
    }
    REPAIR_LOG {
        uuid id PK
        uuid query_audit_id FK
        int attempt_number
    }
1. Module layout
app/sql_agent/
├── __init__.py
├── config.py                 # SqlAgentSettings — own connection strings, model tiers, etc.
├── router.py                  # test-harness endpoints for now (see §9) — not the real integration surface
├── schemas.py                  # ProposeRequest/ProposeResponse, ExecuteRequest/ExecuteResponse, etc.
├── errors.py                    # SqlAgentError hierarchy
├── control_db/
│   ├── session.py                # OWN async engine/session — separate DB, separate connection string, nothing shared with app/db/session.py
│   └── models.py                  # sql_agent_* SQLAlchemy models, own Base — not app.db.models.Base
├── target_db.py                    # read-only engine/session manager for a workspace's target DB (Kalaam's DB)
├── ingestion/
│   ├── introspect.py                 # information_schema introspection against a target DB
│   ├── auto_describe.py               # LLM-drafted table descriptions when none are hand-authored yet
│   ├── loader.py                       # loads a workspace's optional hand-authored YAML enrichment
│   ├── diff.py                          # hash-based change detection vs stored metadata
│   ├── embed.py                           # batched (re-)embedding of changed rows only
│   └── run.py                              # `python -m app.sql_agent.ingestion.run --workspace kalaam`
├── llm/
│   └── models.py                            # provider-agnostic chat-model factory, per-node tier lookup
├── validation/
│   └── sql_guard.py                          # sqlglot-based static validator — SAFETY, not correctness (see §6)
├── graph/
│   ├── state.py                               # LangGraph state TypedDict
│   ├── nodes.py                                 # node functions
│   └── build.py                                  # StateGraph assembly + conditional edges + the propose/execute interrupt
├── eval/
│   ├── golden_set.yaml                          # the growing (question, expected_tables, expected_sql_shape) set — §8
│   └── run_eval.py                                # scores a graph run against golden_set.yaml
├── prompts/
│   ├── prompt_enhance.md
│   ├── ambiguity_check.md
│   ├── table_select.md
│   ├── sql_generate.md
│   ├── sql_critic.md
│   └── repair.md
└── workspaces/
    └── kalaam.yaml                                 # optional hand-authored enrichment: descriptions, glossary, examples, instructions
The sql_agent_* tables live in a new dedicated Postgres database (recommend: a new database, e.g. sql_agent_db, on the same local Postgres server for now — zero new infra to stand up, a connection-string change later if it needs its own instance). Schema setup uses a plain SQLAlchemy Base.metadata.create_all() bootstrap for now, not a formal Alembic chain — this schema will move fast early on; formal migrations are a cheap upgrade once it stabilizes.

2. Control-plane schema (new dedicated sql_agent_db, not turing's DB)
sql_agent_workspaces — id (uuid pk), name (unique), slug, description, status, row_scoping_enabled (bool, default false — generic per-caller row-level scoping hook), timestamps.
sql_agent_datasources — id, workspace_id (fk, 1:1 for v1), dialect, connection_env_var (name of the env var holding the real read-only connection string — never the credential itself), read_only_role_name, statement_timeout_ms, default_row_limit, timestamps.
sql_agent_tables — id, workspace_id, schema_name, table_name, description, is_reviewed (bool, default false — LLM-guessed vs. human-confirmed), row_count_estimate, is_active, source_hash, embedding (Vector(dim)), timestamps. Unique (workspace_id, schema_name, table_name).
sql_agent_columns — id, table_id (fk), column_name, data_type, is_nullable, is_primary_key, is_foreign_key, description, is_reviewed, sample_values (jsonb, optional), is_sensitive (PII flag). (No embedding column — retrieval only needs table-level granularity.) Unique (table_id, column_name).
sql_agent_relationships — id, workspace_id, from_table_id, from_column, to_table_id, to_column, relationship_type (fk_auto/manual), join_hint.
sql_agent_glossary — id, workspace_id, term, definition, maps_to_table_id (nullable), maps_to_column_id (nullable), embedding.
sql_agent_examples — id, workspace_id, question, sql_text, tables_used (jsonb), is_verified (bool), embedding.
sql_agent_query_audit — id, workspace_id, request_id, question, enhanced_question, selected_tables (jsonb), generated_sql, final_sql, critic_notes (jsonb), validation_result (jsonb), repair_attempts, status (proposed/executed/clarify_needed/validation_failed/repair_exhausted/execution_error/blocked/execution_low_confidence), row_count, execution_ms, llm_tokens_used (jsonb per node), model_versions (jsonb, incl. prompt versions), created_at.
sql_agent_repair_log — id, query_audit_id (fk), attempt_number, trigger (validator/critic/explain_guard), failed_sql, error_detail, repaired_sql, created_at.
No pgvector index (ivfflat/hnsw) needed at this scale — plain sequential scan over embedding <=> is fine; revisit only if row counts grow by orders of magnitude.

3. Ingestion pipeline (the "frequent changes" + "no metadata yet" answer)
Two inputs merge into a workspace's metadata:

Auto-introspection (introspect.py) against the target DB's information_schema — read-only connection, produces raw table/column/FK-relationship rows, description = NULL.
Optional hand-authored YAML (workspaces/kalaam.yaml) — descriptions, glossary, curated examples, custom instructions, sensitive-column flags. Connection strings never go in this file.
diff.py hashes each row; unchanged hashes skip re-embedding/re-processing — the lever for editing schema/details often without burning tokens. Rows missing from a fresh introspection are soft-deleted (is_active=false), never hard-deleted (keeps historical audit rows valid).

Bootstrapping with no metadata yet (your current state):

v1 ingestion runs on introspection alone — purely structural. Usable immediately, weaker retrieval until descriptions exist.
ingestion/auto_describe.py — one cheap-tier LLM call per table drafts a description from structure alone, stored is_reviewed=false. Prioritize reviewing whichever tables show up in low-confidence runs.
Zero seed examples is a supported starting state — example_retrieve returns empty gracefully, sql_generate's prompt has an explicit no-examples branch. The example bank grows from verified successful runs (this is the single biggest long-term accuracy lever — see §7).
Relationships rely on auto-detected FKs only for v1; undeclared joins get added manually once a gap is noticed via the agent's own low-confidence/critic flags.
Run via python -m app.sql_agent.ingestion.run --workspace kalaam; the same function later backs an ingest endpoint.

4. LangGraph pipeline (propose, then execute)
State: question, workspace_id, enhanced_question, candidate_tables, selected_tables, pruned_schema, examples, generated_sql, explanation, confidence, critic_notes, validation_errors, repair_count, final_sql, execution_result, plus audit fields. See the pipeline diagram above.

workspace_resolve (deterministic) — v1 has one workspace; real node so multi-workspace routing slots in later.
prompt_enhance (LLM, cheap tier) — expands glossary terms, resolves relative dates, rejects write-intent questions before spending generation tokens.
ambiguity_check (LLM, cheap tier) — detects when the question is genuinely underspecified in a way that would change the SQL (e.g. an undefined metric, no default time range where one materially matters). If ambiguous past a threshold, short-circuits straight to a clarify outcome — returns a clarifying question instead of guessing. This is a deliberate accuracy lever: silently picking an interpretation is a worse failure than asking.
table_retrieve (deterministic, hybrid search) — embeds the question and cosine-searches sql_agent_tables/glossary embeddings, plus a lexical/exact-substring pass over table/column names (catches literal name matches embedding similarity alone can miss), expands via sql_agent_relationships for directly-joined tables, returns top-K.
table_select (LLM, cheap/mid tier) — narrows to the actually-needed table subset; structured output.
column_prune (LLM, cheap tier) — filters to relevant columns for selected tables only; always keeps PK/FK columns for joins.
example_retrieve (deterministic vector search) — top-N examples filtered to selected tables (empty if none exist yet).
sql_generate (LLM, strongest tier) — structured output {sql, explanation, tables_used, confidence}. explanation is the plain-language account surfaced to the caller before execution.
Conditional: confidence below threshold → multi_candidate_generate (N=3 alternative candidates via varied temperature/framing) → candidate_vote (LLM judge or majority-agreement picks the best, or escalates to clarify if candidates diverge irreconcilably) — cost-gated, only triggers on genuinely uncertain generations, preserving token efficiency for the common case.
sql_critic (LLM, mid tier) — a semantic review distinct from the syntax/whitelist validator: given the question + schema + generated SQL, checks for logical errors (wrong join direction, wrong aggregation, a filter the question implied but the SQL omitted, off-by-one date ranges). Issues found → repair with the critic's specific note.
validate (deterministic, sqlglot) — safety/syntax check, see §6. Produces validation_errors.
Conditional routing: clean → explain_guard; errors and repair_count < MAX → repair; budget exhausted → audit with status=repair_exhausted (fail closed).
repair (LLM, mid tier) — regenerates using either the validator's or the critic's specific error (both draw from the same shared repair budget); loops back to validate.
explain_guard (deterministic) — runs Postgres EXPLAIN via the read-only connection; catches runtime-only errors and absurd cost/row estimates. Failure routes back to repair.
⏸ Interrupt (LangGraph checkpoint) — the propose/execute boundary. Caller gets {sql, explanation, tables_used, confidence, critic_notes, audit_id} — nothing has touched Kalaam's DB yet.
execute (deterministic, on a distinct resume call) — runs the validated query via the read-only DB role, statement_timeout enforced, rows capped at default_row_limit.
result_sanity_check (deterministic + optional cheap LLM) — checks execution results for red flags: zero rows where the question implies data should exist, an implausible row count, an all-null aggregate. Flags a caveat on the response rather than silently trusting a syntactically-valid-but-semantically-wrong result. Does not auto-retry against the target DB (avoids unnecessary production load) — it surfaces the caveat for a human to judge.
audit (deterministic) — always runs, at both the propose pause and after execute, recording every stage including critic notes and sanity-check flags.
5. Accuracy engineering (how this gets to battle-tested / 95%)
This is distinct from §6 (safety/validation) — safety stops dangerous SQL from running; this is about stopping wrong-but-safe SQL from being trusted. The levers, in the order they matter:

The verified example bank is the dominant lever. Per Uber's own findings, few-shot examples do more for correctness than almost anything else. The feedback loop (§3: successful, human-glanced-at queries get promoted to sql_agent_examples with is_verified=true) should be treated as an ongoing operational habit, not a one-time seeding task — accuracy climbs with usage, not just with better prompts.
Ambiguity detection over silent guessing (ambiguity_check) — a wrong answer to a question the agent should have asked about is worse than admitting uncertainty.
Semantic critique separate from syntax validation (sql_critic) — catches the failure mode that's hardest to prevent otherwise: SQL that parses fine, references real tables/columns, and executes cleanly, but answers the wrong question (wrong join, wrong aggregation, silently dropped filter).
Confidence-gated multi-candidate generation — only pay for 3x generation cost on the genuinely uncertain fraction of questions; the common case stays cheap.
Hybrid retrieval (embedding + lexical) — pure semantic similarity can miss an exact column-name match; a cheap deterministic lexical pass is a safety net for it.
Post-execution result sanity-checking — catches the "looks plausible, syntactically valid, semantically wrong" case that slips past both the critic and the validator, by inspecting the shape of what actually came back.
Golden-set regression gating — no prompt or model-tier change ships without re-running the golden-set eval (§8) and confirming accuracy didn't regress. model_versions/prompt versions are already captured per-query in sql_agent_query_audit, enabling before/after comparison and rollback.
Description review, prioritized by evidence — is_reviewed=false descriptions that keep showing up in low-confidence/critic-flagged/ambiguous runs are exactly the ones worth hand-correcting first; this turns review into a targeted activity instead of a blind slog through every table.
Being direct: none of this makes 95% true on day one against a schema with zero reviewed descriptions and zero examples. It's what the number is built toward — via the eval loop in §8 — not a property of the architecture alone.

6. Validation/safety layer (defense in depth — dangerous, not just wrong)
App-level (validation/sql_guard.py, deterministic, no LLM):

Parse with sqlglot; reject on parse failure.
Reject anything but exactly one top-level SELECT/WITH statement — no trailing statements, no DML/DDL, no dangerous functions (pg_read_file, dblink, lo_*, etc.).
Walk the AST's table/column references; every one must exist in sql_agent_tables/columns (is_active=true) for the workspace — hallucinated tables/columns are caught deterministically before ever reaching the DB, feeding repair.
Inject/enforce LIMIT ≤ default_row_limit.
Generic row-scoping hook (inert until row_scoping_enabled): when on, requires a specific WHERE <scope_column> = :scope_value predicate, rejects if the LLM's own SQL conflicts with it.
DB-level, on Kalaam's DB (prerequisite you provision — the last line of defense):

A dedicated sql_agent_readonly Postgres role, GRANT SELECT only on in-scope schemas/tables — not superuser, not a writer role.
statement_timeout set on the role, plus default_transaction_read_only=on on the connection.
Point at a read replica of Kalaam's DB if one exists.
7. API surface (test harness only for now — real integration deferred)
Scoped as a way to develop/evaluate the agent itself, not the final integration (kalaam_backend calling in is later work):

POST /sql-agent/workspaces/{id}/ingest — trigger ingestion.
POST /sql-agent/propose — {workspace_id, question} → {sql, explanation, tables_used, confidence, critic_notes, audit_id} — runs the graph up to the pre-execute interrupt, does not touch Kalaam's DB.
POST /sql-agent/execute/{audit_id} — resumes the paused graph and runs the validated query, returns results (+ any sanity-check caveat).
GET /sql-agent/audit/{id} — inspect a past run's full trace.
POST /sql-agent/examples/{audit_id}/verify — promotes a propose+execute run's SQL into sql_agent_examples as is_verified=true (the example-bank feedback loop from §5).
Where this mounts is not load-bearing right now — internal tooling until the real kalaam_backend integration is designed later.

8. Evaluation harness — how "95%" gets measured and driven
Add pytest, pytest-asyncio to requirements-dev.txt; new tests/sql_agent/ directory plus app/sql_agent/eval/.

sql_guard.py unit tests — highest value, no DB/LLM needed: every rejection case against plain SQL strings. Build/test before any graph/LLM code exists.
Ingestion diff unit tests — hash-based change detection, in-memory fixtures.
Golden-set eval (eval/golden_set.yaml + eval/run_eval.py) — the accuracy measurement itself: a growing set of (question, expected_tables, expected_sql_shape) pairs run through the full graph, scored on: table-selection overlap, execution success, ambiguity/critic-flag rate, and human-judged correctness on a sample (mirrors Uber's intent-accuracy/table-overlap/execution-success metrics). This is the thing that's rerun before any prompt/model change ships (§5.7).
Skip automated integration tests against the live Kalaam DB for now — manual smoke testing covers that.
On the 95% target directly: it will not be true on day one against zero reviewed descriptions and zero examples — retrieval/selection quality depends heavily on description/example quality. It's reached iteratively: review descriptions flagged by low-confidence/critic/ambiguity signals, grow the verified example bank from real usage, tune prompts against the golden set as it grows, and gate every change through re-running the eval. Expect the first days of real questions to run well below 95% while metadata is thin, climbing as §5's levers accumulate evidence.

9. New dependencies & config
requirements.txt: langchain, langgraph, langchain-core, langchain-anthropic, langchain-openai, sqlglot, pgvector (SQLAlchemy binding).

requirements-dev.txt: pytest, pytest-asyncio.

New app/sql_agent/config.py (SqlAgentSettings, own pydantic-settings class, not merged into turing's Settings):

sql_agent_control_db_url: str          # the NEW dedicated Postgres DB — separate from turing's database_url
kalaam_readonly_database_url: str      # target DB — read-only creds
anthropic_api_key: str | None
openai_api_key: str | None
sql_agent_model_generate: str          # e.g. "anthropic:claude-sonnet-5" #I will use light models in this project by the way.
sql_agent_model_select: str
sql_agent_model_prune: str
sql_agent_model_critic: str
sql_agent_model_repair: str
sql_agent_embedding_model: str = "text-embedding-3-small"
sql_agent_embedding_dim: int
sql_agent_max_repair_attempts: int = 2
sql_agent_confidence_threshold: float = 0.7     # below this -> multi-candidate generation
sql_agent_multi_candidate_count: int = 3
sql_agent_default_row_limit: int = 200
sql_agent_statement_timeout_ms: int = 10000
10. Build checklist (full, sequenced for execution order)
Phase 1 — foundations through raw schema introspection
Prerequisites (NEEDS FROM YOU):
 Read-only Postgres role on Kalaam's DB (GRANT SELECT only, in-scope schemas/tables); connection string; statement_timeout set on the role.
 Anthropic and/or OpenAI API key for generation; OpenAI API key for embeddings.
 A target for the new dedicated control-plane database (recommend: a new database on your existing local dev Postgres server, e.g. sql_agent_db).
(Not required yet: table descriptions, glossary, example queries.)
Add dependencies + config (§9), plus .env.example entries.
Control-plane DB bootstrap — new database, CREATE EXTENSION IF NOT EXISTS vector, control_db/models.py + control_db/session.py, create_all() bootstrap script.
target_db.py — read-only async engine/session for Kalaam's DB, default_transaction_read_only=on.
ingestion/introspect.py dry run — structured in-memory table/column/FK output from Kalaam's DB, no persistence yet. (NEEDS FROM YOU: review the raw output together.)
Phase 2 — ingestion + safety backbone
ingestion/auto_describe.py + loader.py + optional workspace YAML.
ingestion/diff.py + embed.py — first full ingestion run into sql_agent_db.
validation/sql_guard.py + unit tests (can start in parallel with Phase 1 once step 3's models exist).
llm/models.py provider-agnostic factory.
Phase 3 — the graph, accuracy-hardened
Core nodes: workspace_resolve → table_retrieve (hybrid) → example_retrieve (pure retrieval, testable against Phase 2's ingested data).
Generation nodes: prompt_enhance → ambiguity_check → table_select → column_prune → sql_generate.
Accuracy nodes: multi_candidate_generate + candidate_vote, sql_critic.
Safety/repair loop: validate (reuse step 8) → repair → explain_guard.
Execution side: the propose/execute interrupt, execute, result_sanity_check, audit.
graph/build.py — StateGraph assembly + all conditional edges + the interrupt.
Phase 4 — harness, eval, and closing the loop
router.py test-harness endpoints (§7), including the example-verification endpoint.
eval/golden_set.yaml seeded with your first real questions + eval/run_eval.py.
Run the eval, hand-check every result, correct flagged descriptions, iterate toward the 95% target (§8).
Manual end-to-end smoke test (§Verification).
11. Open risks / decisions still open
Control-plane DB placement: recommended a new database on the existing local dev Postgres server — say if you want a genuinely separate instance/container instead (config difference, not a redesign).
Confidence threshold / multi-candidate count (§9 defaults: 0.7 / 3) are starting points, tune against the golden set.
Kalaam DB replica availability — determines primary-vs-replica blast radius if something slips past the validator.
1 workspace = 1 datasource for v1 — schema already supports more; adding one later is a config/ingestion addition, not a redesign.
Model-tier choices in §9 are placeholders pending provider-key decisions.
Not replicating the reference PDF's 19-file documentation structure — most of it (README ceremony, repo standards, a dedicated future-work doc) is redundant with this repo's conventions and with keeping this feature's data fully separate anyway. The breakdown above is the spec.

Verification
Bootstrap runs clean against the new sql_agent_db; tables exist, pgvector extension active.
Introspection dry-run against Kalaam's DB returns a table/column/FK list matching expectations.
sql_guard.py unit tests pass, including every rejection case.
propose on a golden-set question returns SQL + explanation without touching Kalaam's DB; execute on the same audit_id then runs it and returns results.
Deliberately try a write-intent question (e.g. "delete all calls") — confirm it's rejected before ever reaching Kalaam's DB.
Manually attempt an INSERT using the sql_agent_readonly credentials directly (outside the app) — confirm Postgres itself rejects it, not just the app-level validator.
ruff check . / mypy . clean on all new code.
pytest tests/sql_agent/ and eval/run_eval.py both pass/report.