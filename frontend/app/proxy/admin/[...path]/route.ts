// Server-side admin proxy — injects X-Admin-Key from a server-only env var.
// The browser NEVER holds the admin key.
// Returns 404 when TURING_ADMIN_KEY is unset, making a public deploy safe.
// Also requires a valid signed operator session cookie — this is the real
// security boundary (middleware only does a cheap presence check on the edge).

import { hasValidOperatorSession } from "../../../../lib/operatorSession";

export const dynamic = "force-dynamic";

const ADMIN_KEY = process.env.TURING_ADMIN_KEY ?? "";
const API_URL = process.env.TURING_API_URL ?? "http://localhost:8005";

async function handle(req: Request, { params }: { params: { path: string[] } }) {
  if (!ADMIN_KEY) {
    return new Response("Not found", { status: 404 });
  }

  if (!hasValidOperatorSession()) {
    return new Response(JSON.stringify({ detail: "Unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const path = params.path.join("/");
  const url = new URL(req.url);
  const target = `${API_URL}/v1/admin/${path}${url.search}`;

  const headers: Record<string, string> = {
    "X-Admin-Key": ADMIN_KEY,
    "Content-Type": "application/json",
  };

  const body = req.method === "GET" || req.method === "HEAD" ? undefined : req.body;

  const upstream = await fetch(target, {
    method: req.method,
    headers,
    body,
    // @ts-expect-error — Node 18 fetch accepts duplex
    duplex: body ? "half" : undefined,
  });

  const responseHeaders: Record<string, string> = {
    "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
  };

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };
