# SQL Builder Agent - Integration Guide

This guide is for internal services that need to convert a natural-language
question into a validated PostgreSQL query string.

The SQL Builder Agent only builds SQL. It does not execute the query and does
not return database rows.

## Endpoint

```http
POST /v1/sql-agent/query
X-API-Key: <service-api-key>
Content-Type: application/json
```

The endpoint is protected by the same `X-API-Key` auth used by other `/v1`
business endpoints.

## Request

```json
{
  "question": "How many patients registered last month?",
  "workspace": "kalaam"
}
```

Fields:

| Field | Required | Description |
|---|---:|---|
| `question` | yes | Natural-language question to convert into SQL. |
| `workspace` | no | Workspace slug. Defaults to `kalaam`. Currently only `kalaam` is supported. |

Minimal request:

```json
{
  "question": "How many patients registered last month?"
}
```

## Response

Handled SQL-builder outcomes return HTTP `200`. Callers must branch on
`status`, not only on the HTTP status code.

```json
{
  "status": "built",
  "sql": "SELECT COUNT(*) AS patient_count FROM patients LIMIT 200",
  "dialect": "postgresql",
  "validated": true,
  "explanation": "Counts patients.",
  "tables_used": ["patients"],
  "confidence": 0.92,
  "critic_notes": "The SQL answers the request.",
  "clarifying_question": null,
  "reason": null
}
```

Response fields:

| Field | Description |
|---|---|
| `status` | One of `built`, `clarify_needed`, `blocked`, `repair_exhausted`. |
| `sql` | Validated SQL string. Present only when `status == "built"`. |
| `dialect` | SQL dialect. Currently `postgresql`. |
| `validated` | `true` only when the generated SQL passed static validation and enabled runtime validation. |
| `explanation` | Short explanation of the generated query. |
| `tables_used` | Physical tables referenced by the validated SQL. |
| `confidence` | Model confidence score from `0.0` to `1.0`. |
| `critic_notes` | Semantic review notes from the SQL critic stage. |
| `clarifying_question` | Present when `status == "clarify_needed"`. |
| `reason` | Present for blocked or failed handled outcomes. |

## Status Handling

### `built`

The SQL was generated and validated. The caller may execute `sql` using its own
database connection and data-access policy.

```json
{
  "status": "built",
  "sql": "SELECT COUNT(*) AS patient_count FROM patients LIMIT 200",
  "validated": true
}
```

### `clarify_needed`

The question is too vague to answer safely. Do not execute anything. Ask the
user or upstream workflow for the missing detail.

```json
{
  "status": "clarify_needed",
  "sql": null,
  "validated": false,
  "clarifying_question": "Which date field should be used for this report?"
}
```

### `blocked`

The request appears to ask for a write, destructive action, or otherwise
unsupported operation. Do not retry automatically.

```json
{
  "status": "blocked",
  "sql": null,
  "validated": false,
  "reason": "Write intent is not allowed."
}
```

### `repair_exhausted`

The agent could not produce valid SQL within the repair budget. Do not execute
anything. The caller can show a generic failure or route the question for review.

```json
{
  "status": "repair_exhausted",
  "sql": null,
  "validated": false,
  "reason": "Could not produce valid SQL within the repair budget."
}
```

## HTTP Errors

These represent infrastructure or request-level failures, not normal query
outcomes.

| HTTP | Meaning |
|---:|---|
| `401` | Missing or invalid `X-API-Key`. |
| `422` | Malformed request body. |
| `502` | LLM/provider failure. |
| `500` | Unexpected server error. |

Standard error envelope:

```json
{
  "error": "llm_error",
  "message": "Model provider failed.",
  "detail": {
    "provider": "google_genai"
  },
  "request_id": "..."
}
```

## Example: curl

```bash
curl -X POST "https://<turing-host>/v1/sql-agent/query" \
  -H "X-API-Key: $TURING_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":"How many patients registered last month?","workspace":"kalaam"}'
```

## Example: TypeScript

```ts
type SqlAgentStatus =
  | "built"
  | "clarify_needed"
  | "blocked"
  | "repair_exhausted";

type SqlAgentResponse = {
  status: SqlAgentStatus;
  sql: string | null;
  dialect: "postgresql";
  validated: boolean;
  explanation?: string | null;
  tables_used: string[];
  confidence?: number | null;
  critic_notes?: string | null;
  clarifying_question?: string | null;
  reason?: string | null;
};

export async function buildSqlQuery(question: string): Promise<string> {
  const response = await fetch(`${process.env.TURING_BASE_URL}/v1/sql-agent/query`, {
    method: "POST",
    headers: {
      "X-API-Key": process.env.TURING_API_KEY!,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ question, workspace: "kalaam" }),
  });

  if (!response.ok) {
    throw new Error(`SQL builder request failed: HTTP ${response.status}`);
  }

  const body = (await response.json()) as SqlAgentResponse;

  if (body.status !== "built" || !body.sql) {
    throw new Error(body.clarifying_question || body.reason || body.status);
  }

  return body.sql;
}
```

## Example: Python

```python
import os
import requests


def build_sql_query(question: str) -> str:
    response = requests.post(
        f"{os.environ['TURING_BASE_URL']}/v1/sql-agent/query",
        headers={
            "X-API-Key": os.environ["TURING_API_KEY"],
            "Content-Type": "application/json",
        },
        json={"question": question, "workspace": "kalaam"},
        timeout=120,
    )
    response.raise_for_status()
    body = response.json()

    if body["status"] != "built" or not body.get("sql"):
        raise RuntimeError(
            body.get("clarifying_question") or body.get("reason") or body["status"]
        )

    return body["sql"]
```

## Caller Responsibilities

- Execute SQL only when `status == "built"` and `validated == true`.
- Treat non-`built` statuses as no-query outcomes.
- Apply the caller's own data-access policy before executing the returned SQL.
- Do not expose the service API key to browsers or clients.
- Set a client-side timeout; LLM repair can take longer than ordinary API calls.
- Log `status`, `tables_used`, and `request_id` for support/debugging.

