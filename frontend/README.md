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
