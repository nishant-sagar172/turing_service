# Code Review — Findings & Remediation Plan

**Date:** 2026-08-11
**Reviewed tree:** `turing_service` @ `main` (working tree, uncommitted changes included)
**Method:** three parallel review agents with disjoint scopes, followed by independent verification of every `critical`/`high` finding by the orchestrator (code re-read + executable proofs against `sql_guard`).

| Reviewer | Scope | Findings |
|---|---|---|
| A | `main.py`, `middleware.py`, `dependencies.py`, `auth.py`, `errors.py`, `routers/*`, `schemas/*` | 14 |
| B | `services/*`, `core/*`, `config.py`, `db/*`, `alembic/versions/*`, `docker-compose.yml`, `requirements.txt`, `.env.example` | 18 |
| C | `sql_agent/**`, `tests/**`, `frontend/{app,components,lib}`, `pyproject.toml` | 18 |

**Total: 50 findings** — 2 critical, 9 high, 16 medium, 23 low.

Every fix below is designed to **preserve existing behaviour**. The seven places where behaviour intentionally changes are flagged with a **⚠ Contract change** note.

---

## 0. Verification notes (corrections to the raw agent reports)

The reviewers' SQL-guard claims were re-tested empirically rather than taken on trust. Results:

```
rejected  SELECT INTO (new tbl)  -> unknown_table      # incidental, not a write check
ACCEPTED  SELECT INTO (allowlisted tbl)                # real guard defect
rejected  SELECT INTO TEMP       -> unknown_table      # incidental
ACCEPTED  FOR UPDATE                                   # real guard defect
ACCEPTED  FOR SHARE                                    # real guard defect
ACCEPTED  dblink_send_query('h','SELECT 1')            # real guard defect
ACCEPTED  pg_ls_logdir()                               # real guard defect
rejected  UNION / UNION ALL / EXCEPT -> non_select     # false rejection (C-15)
ACCEPTED  UNION nested inside a CTE                    # inconsistent with the above
```

Two adjustments to the reported severities, both grounded in `app/sql_agent/target_db.py:81-82`, which **does** enforce `default_transaction_read_only=on` and a per-connection `statement_timeout`:

- **C-4 (`SELECT INTO`) and C-5 (`FOR UPDATE`) downgraded `high` → `medium`.** The guard accepts them, but the read-only transaction blocks execution at the Postgres layer. They are defence-in-depth defects, not live exploits.
- **C-2 (`dblink_*`, `pg_ls_*dir`) confirmed at `critical`.** These are *reads*, so `default_transaction_read_only` does not mitigate them at all. This is the one guard gap with no second line of defence — severity depends only on whether the `dblink` extension is installed and what the `sql_agent_readonly` role may execute.
- **New observation not in any report:** `UNION` is rejected at top level but **accepted inside a CTE**. This proves the `non_select` check is not a security boundary — it is purely an accidental functional restriction, which strengthens the case for fixing C-15 rather than relying on it.

Reviewer B's audit of the six Alembic migrations against `app/db/models.py` found zero drift — the only area of the codebase with no findings.

---

## 1. P0 — Act today

### 1.1 Live OpenAI API key committed to a tracked file (B-1, critical)

**Location:** [.env.example:66](.env.example:66) — present in the working tree; never reached a commit.

```
OPENAI_API_KEY=sk-proj-<REDACTED — rotate at OpenAI>
```

A full-length, current-format `sk-proj-` project key, sitting in a template file whose entire purpose is to be copied. The adjacent `GOOGLE_API_KEY=` and `ANTHROPIC_API_KEY=` lines are correctly blank, which makes this line look deliberate rather than accidental.

**Remediation — in this order:**

1. **Rotate the key at OpenAI now.** Treat it as compromised — it sat in a working-tree template file.
2. Blank the line to match its neighbours:
   ```diff
   -OPENAI_API_KEY=sk-proj-<REDACTED>
   +OPENAI_API_KEY=
   ```
3. History scrub is optional and disruptive — the key being dead makes it moot. If the repo is or will be public, run `git filter-repo --replace-text` and force-push with team coordination.
4. Add a secret scanner to CI so this class of leak fails the build:
   ```yaml
   - uses: gitleaks/gitleaks-action@v2
   ```

**Functionality impact:** none — `.env.example` is never loaded at runtime.

### 1.2 Unauthenticated open proxy to the entire admin API (C-1, critical)

**Location:** [frontend/app/proxy/admin/[...path]/route.ts:10-32](frontend/app/proxy/admin/[...path]/route.ts:10)

```ts
async function handle(req: Request, { params }: { params: { path: string[] } }) {
  if (!ADMIN_KEY) return new Response("Not found", { status: 404 });
  // ...no caller check of any kind...
  const headers = { "X-Admin-Key": ADMIN_KEY, "Content-Type": "application/json" };
```

The only gate is whether the **server** has `TURING_ADMIN_KEY` set. There is no session cookie check, no `middleware.ts` anywhere under `frontend/`, and `(operator)/layout.tsx` is a plain client component with no auth logic. Verified by reading the file in full.

**Failure scenario:** anyone who can reach the deployed Next.js host runs
`POST https://<host>/proxy/admin/clients/<uuid>/keys` and receives a freshly issued tenant API key, with the real admin key attached on their behalf. The whole tenant/key/config surface — create clients, issue keys, rewrite webhook secrets, read every client's calls — is open. The comment on line 3 ("Returns 404 when TURING_ADMIN_KEY is unset, making a public deploy safe") describes a guarantee the code does not provide.

**Remediation.** Gate the proxy on an authenticated operator session. Minimum viable version that keeps the existing UX intact:

```ts
// frontend/lib/session.ts
import { cookies } from "next/headers";
import { createHmac, timingSafeEqual } from "node:crypto";

const SECRET = process.env.OPERATOR_SESSION_SECRET ?? "";

export function hasValidOperatorSession(): boolean {
  if (!SECRET) return false;
  const raw = cookies().get("turing_operator")?.value;
  if (!raw) return false;
  const [payload, sig] = raw.split(".");
  if (!payload || !sig) return false;
  const expected = createHmac("sha256", SECRET).update(payload).digest("hex");
  const a = Buffer.from(sig), b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return false;
  const { exp } = JSON.parse(Buffer.from(payload, "base64url").toString());
  return typeof exp === "number" && exp > Math.floor(Date.now() / 1000);
}
```

```diff
 async function handle(req: Request, { params }: { params: { path: string[] } }) {
-  if (!ADMIN_KEY) {
-    return new Response("Not found", { status: 404 });
-  }
+  if (!ADMIN_KEY) return new Response("Not found", { status: 404 });
+  if (!hasValidOperatorSession()) {
+    return new Response(JSON.stringify({ detail: "Unauthorized" }), {
+      status: 401,
+      headers: { "Content-Type": "application/json" },
+    });
+  }
```

Pair it with a `/login` route that verifies an operator credential and sets the signed cookie, plus a `middleware.ts` that redirects unauthenticated `(operator)` page requests to `/login`.

**⚠ Contract change (intended):** the admin UI now requires login. This is the point of the fix. If a login flow is out of scope for this cycle, the interim mitigation is to bind the deployment to a private network / VPN and add an IP allowlist check in the same spot — but that is a deployment control, not a fix, and should be tracked as such.

---

## 2. P1 — SQL guard hardening

The guard is structured as a **denylist** of dangerous functions and expression types. Every bypass found is an instance of "this Postgres feature is not on the reject list." The strategic fix is inversion to an allowlist; the tactical fixes below close the known holes and are worth landing first.

### 2.1 Incomplete dangerous-function denylist (C-2, critical)

**Location:** [app/sql_agent/validation/sql_guard.py:15-29](app/sql_agent/validation/sql_guard.py:15)

Only `pg_ls_dir` is listed, not the `pg_ls_*dir` family; only `dblink`/`dblink_connect`/`dblink_exec`, not `dblink_send_query`/`dblink_get_result`. Both proven accepted above.

**Tactical fix** — prefix matching instead of exact names, so the whole family is covered:

```python
_DANGEROUS_FUNCTIONS = frozenset(
    {
        "copy",
        "lo_export",
        "lo_import",
        "pg_execute_server_program",
        "pg_read_binary_file",
        "pg_read_file",
        "pg_reload_conf",
        "pg_stat_file",
        "query_to_xml",          # can issue an arbitrary nested query
        "query_to_xml_and_xmlschema",
    }
)

# Whole families are blocked by prefix rather than by enumerating members.
_DANGEROUS_PREFIXES = ("lo_", "dblink", "pg_ls_", "pg_read_server_", "pg_logdir_")


def _is_dangerous(name: str) -> bool:
    return name in _DANGEROUS_FUNCTIONS or name.startswith(_DANGEROUS_PREFIXES)
```

Then replace both membership tests in `_reject_writes_and_dangerous_functions` (lines 128 and 135) with `_is_dangerous(name)`. This removes the duplicated `name in _DANGEROUS_FUNCTIONS or name.startswith("lo_")` expression that currently appears twice.

**Strategic fix (recommended follow-up).** Invert to an allowlist. The analytics surface needs a small, enumerable set:

```python
_ALLOWED_FUNCTIONS = frozenset({
    # aggregates
    "count", "sum", "avg", "min", "max", "stddev", "variance",
    "percentile_cont", "percentile_disc", "array_agg", "string_agg",
    # dates
    "date_trunc", "date_part", "extract", "now", "age", "to_char",
    "to_date", "to_timestamp", "make_date", "make_interval",
    # strings / numbers / conditionals
    "lower", "upper", "trim", "btrim", "ltrim", "rtrim", "length",
    "substring", "split_part", "concat", "concat_ws", "replace",
    "round", "floor", "ceil", "abs", "greatest", "least",
    "coalesce", "nullif", "cast",
})


def _reject_unknown_functions(expression: exp.Expression) -> None:
    for node in (*expression.find_all(exp.Func), *expression.find_all(exp.Anonymous)):
        name = (node.sql_name() if isinstance(node, exp.Func) else node.name).lower()
        if name not in _ALLOWED_FUNCTIONS:
            raise GuardError(
                GuardErrorCode.DANGEROUS_FUNCTION,
                f"Function {name!r} is not on the allowlist.",
            )
```

**Migration path that preserves functionality:** ship the allowlist in shadow mode first — log `sql_agent_guard_unknown_function` at WARN without raising, run it across the eval set in `app/sql_agent/eval/`, add every legitimate function that trips it, and only then flip to raising. That way no currently-working question starts failing.

### 2.2 `SELECT ... INTO` bypasses the write check (C-4, medium — downgraded)

**Location:** [app/sql_agent/validation/sql_guard.py:88-93](app/sql_agent/validation/sql_guard.py:88)

sqlglot parses `SELECT id INTO t FROM calls` as `exp.Select` with an `into` arg — not `exp.Create` — so neither the `isinstance(expression, exp.Select)` check nor any member of `_WRITE_EXPRESSIONS` catches it. Verified: rejected only incidentally when the target name isn't allowlisted; **accepted** when it is.

**Fix** — one explicit check in `_reject_writes_and_dangerous_functions`:

```python
def _reject_writes_and_dangerous_functions(expression: exp.Expression) -> None:
    for select in expression.find_all(exp.Select):
        if select.args.get("into") is not None:
            raise GuardError(
                GuardErrorCode.WRITE_OPERATION,
                "SELECT ... INTO creates a table and is not allowed.",
            )
    for expression_type in _WRITE_EXPRESSIONS:
        ...
```

Using `find_all` rather than checking only the top-level node also covers `INTO` inside a CTE or subquery.

### 2.3 `FOR UPDATE` / `FOR SHARE` not rejected (C-5, medium — downgraded)

**Location:** [app/sql_agent/validation/sql_guard.py:70-103](app/sql_agent/validation/sql_guard.py:70). Both verified accepted.

Row locks are meaningless for a read-only analytics agent and cause contention against production tables. Add alongside the `into` check:

```python
    for select in expression.find_all(exp.Select):
        if select.args.get("locks"):
            raise GuardError(
                GuardErrorCode.WRITE_OPERATION,
                "Row-locking clauses (FOR UPDATE / FOR SHARE) are not allowed.",
            )
```

### 2.4 `sensitive: true` columns are never enforced (C-3, high)

**Location:** [app/sql_agent/workspaces/kalaam.yaml:42-60](app/sql_agent/workspaces/kalaam.yaml:42), [app/sql_agent/schema_context.py:201-211](app/sql_agent/schema_context.py:201)

`patients.uhid`, `.name`, `.phone`, `.secondary_phone`, `.email`, `.age` are annotated `sensitive: true`. The **only** consumer of that flag is `_render_column`, which appends the word `"sensitive"` to the column description in the LLM prompt. The allowlist the guard validates against (`ColumnAllowlist = dict[str, frozenset[str]]`) carries no sensitivity metadata at all.

**Failure scenario:** "list patient names and phone numbers for follow-up" produces `SELECT p.name, p.phone FROM patients p LIMIT 2000`, passes `guard_sql`, and is returned with `validated: true`. On a healthcare dataset the flag is decoration the model may ignore at will.

**Fix.** Thread sensitivity into the guard as a parallel structure, leaving the existing `ColumnAllowlist` type untouched so nothing else needs changing:

```python
SensitiveColumns = dict[str, frozenset[str]]


def guard_sql(
    sql: str,
    allowlist: ColumnAllowlist,
    *,
    default_row_limit: int,
    default_schema: str = "public",
    sensitive_columns: SensitiveColumns | None = None,
    allow_sensitive: bool = False,
) -> GuardResult:
    ...
    columns_used = _validate_columns(limited, allowlist, reference_index, default_schema)
    if sensitive_columns and not allow_sensitive:
        _reject_sensitive(columns_used, sensitive_columns)
```

```python
def _reject_sensitive(columns_used: set[str], sensitive: SensitiveColumns) -> None:
    hits = sorted(
        qualified
        for qualified in columns_used
        if qualified.split(".", 1)[1] in sensitive.get(qualified.split(".", 1)[0], frozenset())
    )
    if hits:
        raise GuardError(
            GuardErrorCode.SENSITIVE_COLUMN,
            f"Columns {', '.join(hits)} contain personal data and cannot be selected.",
        )
```

Add `SENSITIVE_COLUMN = "sensitive_column"` to `GuardErrorCode`, populate `sensitive_columns` in `schema_context.load_catalog` from the YAML flag already being parsed, and pass it through from `pipeline.py`.

`allow_sensitive` defaults to `False` (fail closed) and can be lifted per-caller later when an authorization model exists. Because `SENSITIVE_COLUMN` is a `GuardError`, the existing repair loop picks it up automatically and the model gets a chance to rewrite toward an aggregate — so "how many patients did we reach" keeps working while "list their phone numbers" starts failing with an actionable message.

**⚠ Contract change (intended):** questions that previously returned raw PII now return a guard error. That is the fix. Confirm with the product owner which columns should be aggregate-only versus fully blocked before shipping, since the YAML currently marks `age` sensitive alongside `uhid` and `phone`, and age is plausibly needed for cohort analytics.

### 2.5 `UNION` / `EXCEPT` / `INTERSECT` wrongly rejected (C-15, low → functional bug)

**Location:** [app/sql_agent/validation/sql_guard.py:88-93](app/sql_agent/validation/sql_guard.py:88)

Verified: `UNION`, `UNION ALL`, `EXCEPT` all rejected as `non_select` at top level — but **accepted inside a CTE**. So the restriction blocks legitimate queries while providing no safety property.

Any question needing a set operation ("patients contacted by call OR WhatsApp last week") burns the entire repair budget and returns `repair_exhausted`, because the repair prompt has no way to express the answer without a UNION.

**Fix** — accept set operations and validate every branch with the existing logic:

```python
_SET_OPERATIONS: tuple[type[exp.Expression], ...] = (exp.Union, exp.Except, exp.Intersect)

    expression = _parse_single_statement(sql)
    if not isinstance(expression, (exp.Select, *_SET_OPERATIONS)):
        raise GuardError(
            GuardErrorCode.NON_SELECT,
            "Only a single top-level SELECT, WITH, or set-operation query is allowed.",
        )
```

`_reject_writes_and_dangerous_functions`, `_build_reference_index` and `_validate_columns` all already walk with `find_all`, so they traverse both branches unchanged. Only `_enforce_limit` needs care — it is typed `exp.Select` and reads `expression.args["limit"]`. For a set operation, wrap rather than reach inside:

```python
def _enforce_limit_any(expression: exp.Expression, default_row_limit: int) -> exp.Expression:
    if isinstance(expression, exp.Select):
        return _enforce_limit(expression, default_row_limit)
    # Set operations: apply the limit to the whole result, not to either branch.
    limit = expression.args.get("limit")
    if limit is None:
        return expression.limit(default_row_limit, copy=True)
    return _enforce_limit_on_node(expression, limit, default_row_limit)
```

Add a guard test asserting the LIMIT lands on the outer set operation, not on one branch.

### 2.6 `validated=True` is unconditional (C-6, high)

**Location:** [app/sql_agent/pipeline.py:270-279](app/sql_agent/pipeline.py:270), [app/sql_agent/schemas.py:31](app/sql_agent/schemas.py:31)

`BuildQueryResponse.validated` is documented as "True when static and enabled runtime validation passed," but the success branch hardcodes `validated=True`. With `sql_agent_explain_validation=False` only the sqlglot guard ran, yet the caller is told the SQL was runtime-validated.

**Fix** — make the two notions distinct rather than conflated, so no existing consumer breaks:

```python
# schemas.py
class BuildQueryResponse(BaseModel):
    ...
    validated: bool = Field(description="True when the static SQL guard passed.")
    explain_validated: bool = Field(
        default=False,
        description="True when a Postgres EXPLAIN was executed and passed.",
    )
```

```python
# pipeline.py — _explain_if_enabled returns whether it actually ran
async def _explain_if_enabled(...) -> bool:
    if not settings.sql_agent_explain_validation:
        return False
    ...
    return True

# at the call site
explain_ran = await _explain_if_enabled(...)
response = BuildQueryResponse(
    status="built",
    sql=guard.sql,
    dialect=catalog.dialect,
    validated=True,              # static guard did pass — now accurate by definition
    explain_validated=explain_ran,
    ...
)
```

`validated` keeps its current value for every existing caller (additive change, no breakage); `explain_validated` carries the information the docstring was promising.

### 2.7 Statement timeout during EXPLAIN becomes an unhandled 500 (C-7, high)

**Location:** [app/sql_agent/pipeline.py:480-497](app/sql_agent/pipeline.py:480)

```python
        try:
            await session.execute(text(f"EXPLAIN {sql}"))
        except sqlalchemy_exc.OperationalError:
            raise
        except sqlalchemy_exc.SQLAlchemyError as exc:
            raise _ExplainValidationError(str(exc)) from exc
```

`build_query`'s consuming `try/except` catches only `GuardError` and `_ExplainValidationError`. asyncpg's `QueryCanceledError` — raised exactly when the `statement_timeout` from `target_db.py` fires — surfaces as `OperationalError`. So the runaway-query defence turns validation itself into an opaque 500. A transient target-DB blip does the same.

**Fix** — distinguish transient from validation failure, and handle both:

```python
class _ExplainTransientError(RuntimeError):
    """Target DB could not complete EXPLAIN (timeout / connectivity)."""


        try:
            await session.execute(text(f"EXPLAIN {sql}"))
        except sqlalchemy_exc.OperationalError as exc:
            raise _ExplainTransientError(str(exc)) from exc
        except sqlalchemy_exc.SQLAlchemyError as exc:
            raise _ExplainValidationError(str(exc)) from exc
```

In `build_query`, treat a transient error as a repairable signal (the candidate was too expensive — a cheaper rewrite is a legitimate repair) and fall through to `repair_exhausted` rather than crashing:

```python
        except _ExplainTransientError as exc:
            logger.warning("explain_transient_failure: %s", exc)
            last_error = f"Query was too expensive to validate: {exc}"
            continue
```

### 2.8 No timeout on any LLM call (C-8, medium)

**Location:** [app/sql_agent/pipeline.py:452-477](app/sql_agent/pipeline.py:452)

`build_query` makes up to ~10 sequential LLM calls (enhance, ambiguity, table-select, prune, generate ×N, vote, critic ×2, repair ×N) with no `asyncio.wait_for` and no client-level timeout. One hung provider call blocks the request and its worker indefinitely.

**Fix:**

```python
# config.py
sql_agent_llm_timeout_s: float = Field(default=45.0, gt=0, le=300)

# pipeline.py
async def _invoke_structured(...):
    ...
    try:
        return await asyncio.wait_for(
            runnable.ainvoke(prompt),
            timeout=settings.sql_agent_llm_timeout_s,
        )
    except asyncio.TimeoutError as exc:
        raise LLMError(
            f"{tier} model call exceeded {settings.sql_agent_llm_timeout_s}s"
        ) from exc
```

Because `LLMError` is already handled, this degrades to the existing error response instead of hanging. Consider a whole-request ceiling too, since 10 stages × 45 s is still 7½ minutes worst case.

---

## 3. P1 — Correctness in services and routers

### 3.1 `analysis_llm_api_key: null` cannot clear the key (A-1, high)

**Location:** [app/routers/admin.py:293-317](app/routers/admin.py:293); contract documented at [app/routers/admin.py:11](app/routers/admin.py:11)

```python
fields = body.model_dump(exclude_unset=True)
raw_api_key: str | None = fields.pop("analysis_llm_api_key", None)
if raw_api_key is not None:
    ...
```

`pop(..., None)` returns `None` both when the field was omitted **and** when the caller explicitly sent `null` — indistinguishable after the pop. Every other field honours "explicit null clears"; this one silently doesn't. An admin revoking a compromised per-client LLM key via `null` gets a 200 and the encrypted key stays live.

**Fix** — test for presence before popping:

```python
if "analysis_llm_api_key" in fields:
    raw_api_key = fields.pop("analysis_llm_api_key")
    if raw_api_key is None or raw_api_key == "":
        fields["analysis_llm_api_key_enc"] = None
    else:
        fields["analysis_llm_api_key_enc"] = encrypt(raw_api_key, settings.encryption_key)
```

**⚠ Contract change (intended):** `null` now clears, matching the documented behaviour. `""` keeps working, so no existing caller breaks.

### 3.2 Upsert race drops the rest of the batch (B-2, high)

**Location:** [app/services/store.py:166-196](app/services/store.py:166), called from [app/services/batch_sync.py:38](app/services/batch_sync.py:38)

SELECT-then-INSERT against a table with `UniqueConstraint("client_id", "voice_call_id")`. A webhook retry racing the reconcile poll lets both paths see `None` and both INSERT; the loser raises `IntegrityError`, which is uncaught in `sync_batch_executions`'s loop — so **every remaining execution in that pass is silently dropped**.

**Fix — two layers.** First make the upsert atomic:

```python
from sqlalchemy.dialects.postgresql import insert as pg_insert

stmt = (
    pg_insert(Call)
    .values(client_id=resolved_client_id, voice_call_id=execution_id, **mapped_fields)
    .on_conflict_do_update(
        index_elements=["client_id", "voice_call_id"],
        set_=mapped_fields,
    )
    .returning(Call)
)
call = (await session.execute(stmt)).scalar_one()
```

Then make the loop resilient regardless, so one bad item never aborts a pass:

```python
for item in items:
    try:
        await upsert_call_from_execution(session, item, client_id=client_id)
    except Exception:
        logger.exception("skipping execution %s during batch sync", item.get("id"))
        await session.rollback()
        continue
```

Note the `rollback()` — without it the session stays poisoned and every subsequent item fails too.

### 3.3 Unsafe arithmetic on vendor payload (B-3, high)

**Location:** [app/services/store.py:68](app/services/store.py:68)

```python
"cost": payload["total_cost"] / 100 if payload.get("total_cost") is not None else None,
```

`payload` is an untrusted Bolna body. A string `total_cost` raises `TypeError`, which — combined with 3.2 — kills the remaining calls in the pass and returns 500 to Bolna's webhook for what is a single-record data issue.

**Fix:**

```python
raw_cost = payload.get("total_cost")
if isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool):
    cost = raw_cost / 100
else:
    if raw_cost is not None:
        logger.warning(
            "unexpected total_cost type %s for execution %s",
            type(raw_cost).__name__, payload.get("id"),
        )
    cost = None
```

The `bool` exclusion matters: `True / 100` is `0.01` in Python, which would silently record a bogus cost.

Apply the same treatment to every other field read from a vendor payload — see B-18 (`renewal_at`) in §5.

### 3.4 Boolean form values serialized as `"True"` (B-4, high)

**Location:** [app/core/voice_engine.py:134-144](app/core/voice_engine.py:134)

```python
form = {k: (None, str(v)) for k, v in payload.items()}
```

`ScheduleBatchRequest.to_voice_engine_payload()` can include `bypass_call_guardrails: bool`. `str(True)` is `"True"`, not the `"true"` a case-sensitive parser expects — so the caller believes guardrails were bypassed while the wire value says something else. Same trap for any future list/dict field, where `str()` emits a Python repr rather than JSON.

**Fix:**

```python
def _form_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)

form = {k: (None, _form_value(v)) for k, v in payload.items()}
```

### 3.5 N+1 query on every call listing (A-3 / A-8 / A-13, high)

**Location:** [app/routers/calls.py:60-64](app/routers/calls.py:60) used at `:122`; duplicated as `_admin_from_number` at [app/routers/admin.py:664-668](app/routers/admin.py:664) used at `:731` and `:772`

```python
async def _resolve_from_number(session: AsyncSession, call: Call) -> str | None:
    if call.batch_id is None:
        return None
    batch = await session.get(Batch, call.batch_id)
    return batch.from_number if batch else None
```

With `page_size` up to 200, one page issues up to 200 extra sequential round-trips. The list query eager-loads `Call.analysis` but not `Call.batch`, even though the relationship exists at [app/db/models.py:287](app/db/models.py:287).

**Fix** — one eager load removes the helper, the N+1, and the duplication together:

```python
page_query = select(Call).options(
    selectinload(Call.analysis),
    selectinload(Call.batch),
)

def _call_list_item(call: Call) -> CallListItem:
    from_number = call.batch.from_number if call.batch else None
    ...
```

Delete `_resolve_from_number` and `_admin_from_number`. Identical response payloads, one query instead of N+1.

### 3.6 Unbounded query on `list_agent_batches` (A-4, high)

**Location:** [app/routers/batches.py:267-280](app/routers/batches.py:267)

No `.limit()` at all, while the sibling `list_batches` caps at 200. A client with a year of daily batches gets every row in one response.

**Fix.** Match the sibling immediately (`.limit(200)`), then follow up by giving both the same `page`/`page_size`/`total` pagination as `CallListResponse` — see A-9 in §5, which is the same underlying gap.

### 3.7 LLM analysis failures lost permanently (B-5, medium)

**Location:** [app/services/analysis.py:235-242](app/services/analysis.py:235)

```python
except Exception:
    logger.exception("LLM analysis failed for call %s", call.id)
    return None
```

`analyze_call` runs once per terminal transition. A rate limit or momentary 5xx is logged and swallowed; no `call_analysis` row is written and nothing retries. The caller's idempotency check only skips re-running when a row **exists** — it never retries when one doesn't. For a healthcare classifier that flags escalations, the calls that hit transient LLM errors are silently never analysed.

**Fix — two parts.** Retry the transient class:

```python
for attempt in range(3):
    try:
        result = await _call_provider(provider, api_key, model, system, user_content)
        break
    except _RETRYABLE as exc:            # rate limit / 5xx / timeout
        if attempt == 2:
            logger.exception("LLM analysis failed for call %s after retries", call.id)
            return None
        await asyncio.sleep(2 ** attempt)
    except Exception:
        logger.exception("LLM analysis failed permanently for call %s", call.id)
        return None
```

And make the gap observable so a sweep can find it — record the attempt, so "terminal call with no analysis row older than N minutes" becomes a queryable backlog rather than a log line nobody reads.

---

## 4. P2 — Type safety and validation at the boundary

### 4.1 Missing `max_length` on fields backed by bounded columns (A-2, high)

**Location:** [app/schemas/admin.py](app/schemas/admin.py) (`IssueKeyRequest.label`, `ClientConfigUpdate.webhook_secret`), [app/schemas/clients.py](app/schemas/clients.py) (`contact_email` ×3)

`ClientApiKey.label` is `String(128)`, `ClientConfig.webhook_secret` is `String(128)`, `Client.contact_email` is `String(256)`. Over-long input raises asyncpg `StringDataRightTruncation` inside the commit — not a registered type in `app/errors.py` — so it falls through to `_unhandled` and returns a bare 500 for what should be a 422. `RegisterRequest.name` already shows the right pattern with `max_length=128`.

**Fix:**

```python
label: str | None = Field(default=None, max_length=128)
webhook_secret: str | None = Field(default=None, max_length=128)
contact_email: str | None = Field(default=None, max_length=256)   # all three models
```

### 4.2 `EmailStr` imported but never used (A-7, medium)

**Location:** [app/schemas/clients.py:7](app/schemas/clients.py:7)

`EmailStr` is imported and never referenced; every `contact_email` is an unconstrained `str`. The open `/v1/register` endpoint accepts `"not an email"`, which is then used for approval and claim-link delivery.

**Fix:** `contact_email: EmailStr | None = Field(default=None, max_length=256)` on all three models. `UpdateClientRequest`'s `allow_empty_email` validator runs in `mode="before"`, so `""`-clears still works.

**⚠ Contract change (intended):** malformed emails now 422 at the boundary instead of failing silently downstream. Check existing rows for values that would no longer validate before shipping.

### 4.3 Money as float (B-10, medium)

**Location:** [app/services/store.py:68](app/services/store.py:68), [app/db/models.py:281](app/db/models.py:281) (`Call.cost: Mapped[float | None] = mapped_column(Float)`)

Cents are divided by 100 into a binary `Float`, then `func.sum`/`avg`ed across thousands of rows in `analytics.py`. Rounding error accumulates on figures clients will reconcile against an invoice.

**Fix.** Store integer cents (`cost_cents: Integer`) or `Numeric(12, 4)`, and convert only at the API boundary. Migration that preserves values and behaviour:

```python
def upgrade() -> None:
    op.add_column("calls", sa.Column("cost_cents", sa.Integer(), nullable=True))
    op.execute("UPDATE calls SET cost_cents = ROUND(cost * 100) WHERE cost IS NOT NULL")
    # keep `cost` for one release so readers are never broken, then drop in a follow-up
```

Dual-write both columns for one release, cut readers over to `cost_cents`, then drop `cost`. API responses keep returning a float, so no client sees a change.

### 4.4 Unconstrained enum-like query filters (A-10, low)

**Location:** [app/routers/calls.py:71-73](app/routers/calls.py:71), [app/routers/admin.py:676-678](app/routers/admin.py:676)

`status`, `outcome`, `urgency` are bare `str | None`, so `?outcome=Booking` (wrong case) returns an empty page rather than a 422. Two lines below, `granularity` already does this correctly with `Query(default="day", pattern="^(day|week)$")`.

**Fix:** constrain with `Literal[...]` sourced from the shared status module introduced in §6.1, matching the established `granularity` pattern.

### 4.5 Loose types (A-12, A-14, B-16, B-18, C-9, C-10, C-17, C-18)

| ID | Location | Fix |
|---|---|---|
| A-12 | `admin.py:211` `list_keys() -> list` | `-> list[KeySummary]`; every sibling handler already does this |
| A-14 | `admin.py` client CRUD `-> Client` while `response_model=ClientSummary` | Annotate `-> ClientSummary` and `return ClientSummary.model_validate(client)` so mypy checks the real contract |
| B-16 | `models.py` `status`/`outcome`/`urgency` are plain `String` | Add Postgres `CHECK (... IN (...))` for the app-defined `outcome`/`urgency`; leave `Call.status` as text since it mirrors an upstream vocabulary, but validate on write against the shared set from §6.1 |
| B-18 | `phone_number_sync.py:59` `renewal_at` `str()`-coerced into `String(64)` | Parse to `datetime`, log-and-`None` on failure, migrate the column to `DateTime(timezone=True)` like every other timestamp in the schema |
| C-9 | `sql_agent/config.py:48-50` no upper bounds | `multi_candidate_count: Field(default=3, ge=1, le=10)`, `statement_timeout_ms: Field(default=10000, ge=1, le=60000)` — a typo like `100` currently multiplies cost 33× and an oversized timeout defeats the DoS defence |
| C-10 | Row limit hardcoded 2000 (`config.py:49`) vs 200 (`control_db/models.py:101`) | Drop the DDL default; ingestion already overwrites it, so the second number is dead **and** misleading |
| C-17 | `frontend/lib/types.ts` all-optional fields **plus** `[key: string]: unknown` | Remove the index signature on types modelling a known backend schema; make genuinely-present fields required. Keep `Record<string, unknown>` only for open payloads like `extracted_data` |
| C-18 | `frontend/lib/api.ts:71` `getBatchMetrics` returns `Record<string, unknown>` | Add a `BatchMetrics` interface, consistent with every other endpoint |

---

## 5. P2 — Hardcoded and vestigial logic

Grouped because the user specifically asked for unnecessary hardcoding, including branches that no longer serve a purpose.

### 5.1 Dead `__import__` dependency hack (A-6, medium) — **pure vestigial code**

**Location:** [app/routers/admin.py:144](app/routers/admin.py:144), [app/routers/admin.py:440](app/routers/admin.py:440)

```python
settings=Depends(lambda: __import__("app.config", fromlist=["get_settings"]).get_settings())
```

`get_settings` is already imported at line 27 and used correctly at line 289. This lambda re-imports the module on every request to `approve_client` / `get_agent_variables_admin`, and — worse — breaks `app.dependency_overrides[get_settings]` in tests, because the lambda is a different callable identity.

**Fix:** `settings: Settings = Depends(get_settings)`, matching every other handler in the file. No functional change; restores testability.

### 5.2 Nonsensical committed model default (B-12, low) — **vestigial**

**Location:** [.env.example:72-73](.env.example:72)

```
LLM_PROVIDER=openai                    # anthropic | openai
LLM_MODEL=gpt-5.6-luna  # leave blank to use provider default
```

`gpt-5.6-luna` is not a real model id, and the comment says "leave blank" on a line that is not blank. Anyone copying the template inherits a guaranteed failure. The provider also contradicts `config.py`'s own default (`anthropic`).

**Fix:** `LLM_MODEL=` (blank, matching the comment) and align `LLM_PROVIDER` with the code default, or delete both lines since `config.py` already supplies them.

### 5.3 Default credentials as silent fallbacks (B-13, low)

**Location:** [docker-compose.yml:18](docker-compose.yml:18), `:41`; [.env.example:34-35](.env.example:34)

```yaml
POSTGRES_PASSWORD: ${TURING_PG_PASSWORD:-turing}
--requirepass "${TURING_REDIS_PASSWORD:-turing}"
```

The fallback silently "just works," which is exactly what makes it dangerous — a compose file copied to a shared host protects both datastores with a password published in this repo.

**Fix:** drop the `:-turing` defaults so `docker compose up` fails loudly when the vars are unset. Use `${TURING_PG_PASSWORD:?set TURING_PG_PASSWORD}` to make the error self-explanatory.

**⚠ Contract change (intended):** local `docker compose up` now requires a `.env`. Document the one-liner in the README.

### 5.4 Vendor base URL duplicated (B-14, low)

**Location:** [app/core/voice_engine.py:37](app/core/voice_engine.py:37) and [app/config.py:31](app/config.py:31) both hardcode `https://api.bolna.ai`.

**Fix:** make `base_url` a required parameter of `VoiceEngineClient.__init__` so `Settings.voice_engine_base_url` is the single source of truth and every construction site is forced to pass it.

### 5.5 Hardcoded, unpaginated caps (A-9, low)

**Location:** [app/routers/admin.py:324-346](app/routers/admin.py:324) — `.limit(200)` with no `page`/`page_size`/`total`, so batch #201 is unreachable and the truncation is invisible in the response.

**Fix:** give it the `page`/`page_size`/`total` shape already used by `CallListResponse`. Resolves A-4 (§3.6) at the same time.

---

## 6. P3 — Structural cleanups

### 6.1 Single source of truth for call-status vocabulary (B-6, medium)

**Location:** [app/services/store.py:199-203](app/services/store.py:199) and [app/services/analytics.py:36-41](app/services/analytics.py:36) define the same terminal/connected sets independently — and **both are live**: `batch_sync.py` imports `TERMINAL` from `analytics`, `routers/calls.py` imports `TERMINAL_STATUSES` from `store`.

Adding a new Bolna failure code to one and not the other silently corrupts `success_rate`/`connection_rate` in one path while the other stays right — analytics drift with no crash to alert anyone.

**Fix** — new `app/core/call_status.py` as the sole definition:

```python
"""Canonical call-status vocabulary. Single source of truth."""

CONNECTED_STATUSES = frozenset({"completed"})
NOT_CONNECTED_STATUSES = frozenset({
    "no-answer", "busy", "failed", "canceled", "cancelled",
    "stopped", "error", "balance-low",
})
TERMINAL_STATUSES = CONNECTED_STATUSES | NOT_CONNECTED_STATUSES
```

Re-export the old names from both modules for one release so nothing breaks, then remove the aliases. This module also becomes the source for the `Literal` types in §4.4 and the `CHECK` constraints in §4.5.

### 6.2 Service layer importing from the router layer (B-11, low)

**Location:** [app/services/batch_sync.py:31](app/services/batch_sync.py:31)

```python
from app.routers.webhooks import _run_analysis  # lazy: avoids import cycle
```

A service reaching into a private router helper inverts the dependency direction; the lazy import exists only to paper over the resulting cycle. It also makes `sync_batch_executions` untestable without importing the whole router graph.

**Fix:** move `_run_analysis` into `app/services/analysis.py` as a public `run_analysis_for_call(call_id)` and have both `batch_sync.py` and `routers/webhooks.py` import it from there. Pure relocation — no behaviour change.

### 6.3 Duplicated ORM→schema mapping (A-8, medium)

**Location:** `calls.py:27-40`, `calls.py:239-249`, `admin.py:648-661`, `admin.py:813-823` — the same nine-field `CallAnalysisResult(...)` construction, including `or []` defaulting, copied four times across two files.

**Fix:**

```python
# app/schemas/analysis.py
class CallAnalysisResult(BaseModel):
    ...
    @classmethod
    def from_model(cls, analysis: "CallAnalysis | None") -> "CallAnalysisResult | None":
        if analysis is None:
            return None
        return cls(
            outcome=analysis.outcome, summary=analysis.summary, reason=analysis.reason,
            requests=analysis.requests or [], urgency=analysis.urgency,
            confidence=analysis.confidence,
            symptoms_reported=analysis.symptoms_reported or [],
            model_used=analysis.model_used, analyzed_at=analysis.analyzed_at,
        )
```

Replace all four call sites with `CallAnalysisResult.from_model(analysis)`.

### 6.4 Background task can be garbage-collected (A-5, medium)

**Location:** [app/middleware.py:44-47](app/middleware.py:44)

```python
if not path.startswith(_SKIP_PREFIXES):
    import asyncio
    asyncio.create_task(self._record(request, response.status_code, latency_ms, request_id))
```

The event loop holds only a **weak** reference to a task created this way. Under load the `Task` can be collected before it runs, silently dropping the `request_logs` insert — not even the `logger.debug` in `_record` fires, since the coroutine may never execute.

**Fix** (also resolves A-11, the inline `import asyncio` in the hot path):

```python
import asyncio  # module level, alongside logging/time/uuid

_background_tasks: set[asyncio.Task[None]] = set()
...
    task = asyncio.create_task(self._record(...))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
```

### 6.5 Stale variable-override cache (B-7, medium)

**Location:** [app/core/variables.py:71-82](app/core/variables.py:71) — `@lru_cache` on `load_variable_overrides(path)` where `path` is a constant, so the file is read once per process, forever. An operator editing `agent_variables.json` sees no effect until restart, with no log line indicating the edit was ignored.

**Fix** — cache on mtime so edits are picked up without giving up caching:

```python
def load_variable_overrides(path: str) -> dict[str, Any]:
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    return _load_cached(path, mtime)


@lru_cache(maxsize=8)
def _load_cached(path: str, _mtime: float) -> dict[str, Any]:
    ...  # existing body unchanged
```

### 6.6 Unbounded in-memory rate-limit store (B-8, medium)

**Location:** [app/services/rate_limit.py:25](app/services/rate_limit.py:25), `:58-65` — timestamps are pruned *within* a bucket's list, but the bucket key itself is never removed. Every distinct source IP that ever hits `POST /v1/register` leaks a permanent dict entry. This is the Redis-down fallback path — precisely the long-lived scenario where it matters.

**Fix:** drop buckets that prune to empty, and cap total size:

```python
window[:] = [t for t in window if now - t < window_seconds]
if not window:
    _attempts.pop(bucket, None)
```

Or switch to `cachetools.TTLCache(maxsize=10_000, ttl=window_seconds)` for automatic eviction.

### 6.7 Missing composite index for the analytics hot path (B-9, medium)

**Location:** [app/db/models.py](app/db/models.py) (`Call.created_at`, no index), consumed by [app/services/analytics.py:56-59](app/services/analytics.py:56) and `:410-420`

Every analytics query filters `Call.created_at` between two dates, and `get_timeseries` additionally `GROUP BY date_trunc(...)` on it. `Call` is indexed on `client_id`, `batch_id`, `contact_number`, `patient_ref`, `voice_call_id` — but not `created_at`.

**Fix** — one migration serving both the tenant filter and the date range:

```python
def upgrade() -> None:
    op.create_index("ix_calls_client_created", "calls", ["client_id", "created_at"])
```

### 6.8 No retry on transient voice-engine transport errors (B-15, low)

**Location:** [app/core/voice_engine.py:65-72](app/core/voice_engine.py:65) — there is a timeout but zero retry for `httpx.RequestError`. For `make_call`/`create_batch`, one DNS blip means a patient call that should have gone out simply doesn't.

**Fix:** bounded retry (2–3 attempts, exponential backoff) on `httpx.RequestError`/`httpx.TimeoutException` **only**. Never retry a received non-2xx — that is a real application error. Confine retries to idempotent GETs and to POSTs where no DB row has been committed yet, so a retry can't double-place a call.

### 6.9 Dependency pinning (B-17, low)

**Location:** [requirements.txt:1-22](requirements.txt:1) — floor-only pins throughout, no lockfile. `langchain>=1.0` in particular ships breaking changes across its 1.x line, so two installs on different days can resolve to different trees.

**Fix:** compile a lockfile (`uv pip compile requirements.in -o requirements.txt`) with exact pins and hashes for deployment; keep `>=` ranges in a separate `requirements.in`.

### 6.10 Two schema sources of truth, one wired up (C-11, medium)

**Location:** [app/sql_agent/ingestion/](app/sql_agent/ingestion/), [app/sql_agent/control_db/](app/sql_agent/control_db/) vs [app/sql_agent/pipeline.py](app/sql_agent/pipeline.py)

The live path loads schema context exclusively from `workspaces/<slug>.yaml` + the committed `<slug>.allowlist.json`. Neither `pipeline.py` nor any router imports `control_db` or `ingest_workspace` — the whole pgvector/`QueryAudit`/`RepairLog`/glossary tree is reachable only via standalone `python -m` scripts.

This is either dead code or a second, driftable source of truth for the same metadata, with nothing keeping them consistent. Either is a problem, because a reader auditing the safety story will reasonably assume `control_db` is load-bearing.

**Fix — pick one, explicitly:**
- **(a)** Wire `schema_context.load_catalog` to read from the control DB (the apparent original intent, given the audit and embedding tables), making YAML the ingestion input rather than the runtime source; or
- **(b)** Add a header comment to `ingestion/__init__.py` and `control_db/__init__.py` stating plainly that the subsystem is a future-phase placeholder not yet on the request path, and exclude it from coverage targets.

Option (a) also gives C-12 (below) somewhere structured to write audits.

### 6.11 Audit log leaks PII to plaintext logs (C-12, medium)

**Location:** [app/sql_agent/pipeline.py:544-571](app/sql_agent/pipeline.py:544)

```python
payload = {..., "question": question, "enhanced_question": enhanced_question,
           "final_sql": response.sql, ...}
logger.info("sql_agent_audit %s", json.dumps(payload, sort_keys=True))
```

"Find the record for patient phone 9876543210" flows into `enhanced_question` and into a literal in `final_sql`, landing unredacted in application logs. Combined with §2.4 (sensitive columns unenforced), this is the second place the same PII escapes — from a codebase that carefully annotates which columns are sensitive.

**Fix:** redact literals before logging, keeping the audit's diagnostic value:

```python
_LITERAL = re.compile(r"'[^']*'")

def _redact(sql: str) -> str:
    return _LITERAL.sub("'?'", sql)
```

Log `_redact(response.sql)` and a salted hash of `question` rather than its text. Better still, route the full payload to the `QueryAudit` table (§6.10 option (a)) with column-level redaction, where access is controlled.

### 6.12 Model tier reuse (C-16, low)

**Location:** [app/sql_agent/pipeline.py:317-356](app/sql_agent/pipeline.py:317) — `_prompt_enhance`, `_ambiguity_check` and `_select_tables` all pass the literal tier `"select"`, so one setting controls three unrelated prompts. `ModelTier` defines five tiers for seven prompt stages.

**Fix:** add `sql_agent_model_enhance` / `sql_agent_model_ambiguity` settings and matching tiers, each defaulting to the current `sql_agent_model_select` value so behaviour is unchanged until an operator opts in. If the sharing is deliberate, document it in the `ModelTier` docstring instead.

---

## 7. Regression tests to add

The guard suite currently covers the happy path plus DELETE/UPDATE/INSERT/DROP, `pg_read_file`, unknown table/column, ambiguous column, multi-statement, and non-literal LIMIT — good coverage of what the guard *does* check, and zero coverage of every bypass found here (C-13).

Each of the following should fail against today's code and pass after the corresponding fix.

```python
# tests/sql_agent/test_sql_guard.py

@pytest.mark.parametrize("sql", [
    "SELECT id INTO calls FROM calls",                       # C-4
    "SELECT id INTO TEMP scratch FROM calls",                # C-4
    "SELECT id FROM calls FOR UPDATE",                       # C-5
    "SELECT id FROM calls FOR SHARE",                        # C-5
    "SELECT dblink_send_query('c', 'SELECT 1')",             # C-2
    "SELECT dblink_get_result('c')",                         # C-2
    "SELECT pg_ls_logdir()",                                 # C-2
    "SELECT pg_ls_waldir()",                                 # C-2
])
def test_guard_rejects_bypass(sql: str) -> None:
    with pytest.raises(GuardError):
        guard_sql(sql, ALLOWLIST, default_row_limit=100)


def test_guard_rejects_sensitive_columns() -> None:          # C-3
    with pytest.raises(GuardError) as exc:
        guard_sql("SELECT name, phone FROM patients", ALLOWLIST,
                  default_row_limit=100,
                  sensitive_columns={"patients": frozenset({"name", "phone"})})
    assert exc.value.code is GuardErrorCode.SENSITIVE_COLUMN


@pytest.mark.parametrize("sql", [                            # C-15 — must be ACCEPTED
    "SELECT id FROM calls UNION SELECT id FROM calls",
    "SELECT id FROM calls UNION ALL SELECT id FROM calls",
    "SELECT id FROM calls EXCEPT SELECT id FROM calls",
])
def test_guard_allows_set_operations(sql: str) -> None:
    assert guard_sql(sql, ALLOWLIST, default_row_limit=100).sql
```

Also required:

- **C-14 — fix the test that encodes the bug.** [tests/sql_agent/test_pipeline.py:11-17](tests/sql_agent/test_pipeline.py:11) sets `sql_agent_explain_validation=False` and then asserts `validated is True`, locking in C-6 as expected behaviour. Split into two cases: explain-disabled asserting `explain_validated is False`, and explain-enabled (mocking `target_session`) asserting `explain_validated is True`.
- **A-1:** `PUT /clients/{id}/config` with `{"analysis_llm_api_key": null}` clears `analysis_llm_api_key_enc`.
- **B-2:** two concurrent `upsert_call_from_execution` calls for the same `execution_id` produce one row and no exception.
- **B-3:** `total_cost` as `"12.5"`, `True`, and `None` each yield `cost=None` without raising.
- **B-4:** `schedule_batch` with `bypass_call_guardrails=True` sends the literal `"true"`.
- **A-3:** assert the query count for a 50-row call page is constant (e.g. via SQLAlchemy's `before_cursor_execute` event) — this is the test that keeps the N+1 from returning.
- **C-1:** request to `/proxy/admin/clients` without a session cookie returns 401.

---

## 8. Suggested sequencing

| Order | Work | Findings | Rationale |
|---|---|---|---|
| 1 | Rotate the OpenAI key; blank the line | B-1 | Live credential exposure |
| 2 | Gate the admin proxy | C-1 | Full admin takeover path |
| 3 | Guard hardening + regression tests | C-2, C-4, C-5, C-13 | Small, self-contained, high leverage |
| 4 | Sensitive-column enforcement | C-3, C-12 | Needs a product call on which columns are aggregate-only |
| 5 | Correctness fixes | A-1, B-2, B-3, B-4, C-6, C-7 | Silent data loss and misleading contracts |
| 6 | Perf + validation | A-3, A-4, B-9, A-2, C-8 | N+1, unbounded queries, missing index, timeouts |
| 7 | Type/boundary tightening | A-7, A-10, A-12, A-14, B-10, B-16, B-18, C-9, C-17, C-18 | Mechanical; the money migration needs a dual-write release |
| 8 | Dedupe + structure | A-5, A-6, A-8, A-11, A-13, B-6, B-7, B-8, B-11, C-10, C-16 | Removes the conditions that let 3–7 recur |
| 9 | Decide on `control_db` | C-11 | Wire it up or mark it non-load-bearing |
| 10 | Ops hygiene | B-12, B-13, B-14, B-15, B-17, A-9 | Secret scanning in CI, lockfile, retries, pagination |

---

## Appendix — full finding index

**Critical:** B-1, C-1
**High:** A-1, A-2, A-3, A-4, B-2, B-3, B-4, C-3, C-6, C-7
**Medium:** A-5, A-6, A-7, A-8, A-9, B-5, B-6, B-7, B-8, B-9, B-10, C-4*, C-5*, C-8, C-11, C-12, C-13
**Low:** A-10, A-11, A-12, A-13, A-14, B-11, B-12, B-13, B-14, B-15, B-16, B-17, B-18, C-9, C-10, C-14, C-15, C-16, C-17, C-18

\* Downgraded from `high` after verifying that `target_db.py` enforces `default_transaction_read_only=on`.
