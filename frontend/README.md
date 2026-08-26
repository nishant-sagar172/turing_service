# turing frontend (dev console)

A Next.js (App Router + TypeScript) development console for `turing_service`.
It exercises the backend's Bolna endpoints: dashboard/status, single calls,
batches, and phone-number (caller-ID) selection.

> For development only. Other services integrate with the backend directly.

## How it talks to the backend

All browser requests hit `/api/*`, which Next.js **rewrites** to the backend
(`next.config.mjs`). No CORS setup needed. Point it at the backend with:

```bash
cp .env.local.example .env.local   # then set TURING_API_URL
```

Default: `http://localhost:8005`.

## Operator console login

The operator console (`(operator)` routes) sits behind a shared-password
login, separate from the tenant portal's API-key sign-in. Set in `.env.local`:

```bash
OPERATOR_PASSWORD=some-strong-shared-password
OPERATOR_SESSION_SECRET=a-long-random-string   # signs the session cookie (HMAC-SHA256)
```

`POST /api/login` with `{ "password": "..." }` sets a signed `turing_operator`
cookie; `DELETE /api/login` clears it. `middleware.ts` redirects unauthenticated
requests for operator pages to `/login`. The real authorization check lives in
`/proxy/admin/[...path]/route.ts` (via `lib/operatorSession.ts`), which verifies
the cookie's HMAC before it will forward `X-Admin-Key` to the backend — the
middleware check is edge-runtime and format-only, not the security boundary.

If either env var is unset, `/api/login` returns 503 and the operator console
is effectively disabled (matching how `TURING_ADMIN_KEY` unset returns 404 from
the admin proxy).

## Run

```bash
npm install
npm run dev            # http://localhost:3000
```

Run the backend too (from the repo root):

```bash
uvicorn app.main:app --reload --port 8005
```

## Pages

| Route | What it does |
|---|---|
| `/` | Service health + Bolna connectivity |
| `/calls` | Make a call (caller-ID dropdown, dynamic vars, schedule), track, stop |
| `/batches` | Create batch from JSON recipients, schedule, list, executions, stop/delete |
| `/phone-numbers` | Available caller IDs + configured default |
