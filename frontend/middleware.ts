// Redirects unauthenticated requests for operator console pages to /login.
//
// Edge-runtime note: middleware runs on Vercel's/Next's Edge runtime, which
// does not expose node:crypto (no HMAC verification available here). This
// middleware therefore only does a cheap presence-and-format check on the
// turing_operator cookie (matches `<base64url>.<64 hex chars>`) — good enough
// to bounce obviously-logged-out visitors to /login without a network round
// trip. It is NOT the security boundary: forging a well-formed-looking cookie
// would pass this check, but every actual admin request goes through
// /proxy/admin/[...path]/route.ts, which runs in the Node runtime and calls
// hasValidOperatorSession() (full HMAC + expiry verification via
// lib/operatorSession.ts) before it will inject the real X-Admin-Key. That
// route handler is the real gate; this middleware is only a UX convenience.

import { NextResponse, type NextRequest } from "next/server";

const OPERATOR_COOKIE = "turing_operator";
// payload (base64url) . hmac-sha256 hex digest (64 hex chars)
const COOKIE_FORMAT = /^[A-Za-z0-9_-]+\.[0-9a-f]{64}$/;

export function middleware(req: NextRequest) {
  const cookie = req.cookies.get(OPERATOR_COOKIE)?.value;
  if (cookie && COOKIE_FORMAT.test(cookie)) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", req.url);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // Matches operator console pages only. Explicitly excludes:
  //  - /api/**    (tenant + public backend calls incl. /api/login — never gate)
  //  - /proxy/**  (the admin proxy route handler does its own real auth check)
  //  - /_next/**  (framework internals)
  //  - /login     (the login page itself — avoid a redirect loop)
  //  - /register, /claim/*, /portal (client-facing (public) routes — must stay ungated)
  //  - favicon.ico and any path containing a dot (static assets)
  matcher: ["/((?!api|proxy|_next|login|register|claim|portal|favicon\\.ico|.*\\..*).*)"],
};
