// Operator login — POST {password} sets the signed turing_operator cookie.
// DELETE clears it (logout). Compares against OPERATOR_PASSWORD with a
// timing-safe comparison. 503s if either env var required for auth is unset,
// rather than silently allowing access.

import { timingSafeEqual, createHash } from "node:crypto";
import { cookies } from "next/headers";
import { createSessionCookie, OPERATOR_COOKIE } from "../../../lib/operatorSession";

export const dynamic = "force-dynamic";

const COOKIE_MAX_AGE_SECONDS = 12 * 60 * 60; // 12h, matches operatorSession's default TTL

function timingSafeStringEqual(a: string, b: string): boolean {
  // Hash both sides to a fixed length first so timingSafeEqual never sees a
  // length mismatch (which would throw) and doesn't leak length via timing.
  const aHash = createHash("sha256").update(a).digest();
  const bHash = createHash("sha256").update(b).digest();
  return timingSafeEqual(aHash, bHash);
}

export async function POST(req: Request) {
  const secret = process.env.OPERATOR_SESSION_SECRET ?? "";
  const password = process.env.OPERATOR_PASSWORD ?? "";
  if (!secret || !password) {
    return new Response(
      JSON.stringify({ detail: "Operator login is not configured on this server." }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }

  let body: { password?: unknown } = {};
  try {
    body = await req.json();
  } catch {
    // fall through to validation below
  }

  const submitted = typeof body.password === "string" ? body.password : "";
  if (!submitted || !timingSafeStringEqual(submitted, password)) {
    return new Response(JSON.stringify({ detail: "Incorrect password" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  cookies().set(OPERATOR_COOKIE, createSessionCookie(COOKIE_MAX_AGE_SECONDS * 1000), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: COOKIE_MAX_AGE_SECONDS,
  });

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

export async function DELETE() {
  cookies().delete(OPERATOR_COOKIE);
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
