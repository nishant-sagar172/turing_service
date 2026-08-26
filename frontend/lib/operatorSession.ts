// Operator session — shared-password + HMAC-signed cookie.
// Server-only module (uses node:crypto and next/headers). Never import into a
// client component. Distinct from lib/session.ts (the tenant portal API key
// helper) — this guards the operator console / admin proxy instead.

import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

export const OPERATOR_COOKIE = "turing_operator";

const DEFAULT_TTL_MS = 12 * 60 * 60 * 1000; // 12h

function sign(payload: string, secret: string): string {
  return createHmac("sha256", secret).update(payload).digest("hex");
}

/** Builds `<base64url(JSON{exp})>.<hmac-sha256 hex>` signed with OPERATOR_SESSION_SECRET. */
export function createSessionCookie(ttlMs: number = DEFAULT_TTL_MS): string {
  const secret = process.env.OPERATOR_SESSION_SECRET ?? "";
  const exp = Date.now() + ttlMs;
  const payload = Buffer.from(JSON.stringify({ exp })).toString("base64url");
  const sig = sign(payload, secret);
  return `${payload}.${sig}`;
}

/** Reads the turing_operator cookie and verifies its HMAC + expiry. Never throws. */
export function hasValidOperatorSession(): boolean {
  try {
    const secret = process.env.OPERATOR_SESSION_SECRET ?? "";
    if (!secret) return false;

    const cookie = cookies().get(OPERATOR_COOKIE)?.value;
    if (!cookie) return false;

    const dot = cookie.indexOf(".");
    if (dot <= 0 || dot === cookie.length - 1) return false;

    const payload = cookie.slice(0, dot);
    const sig = cookie.slice(dot + 1);

    const expectedSig = sign(payload, secret);

    const sigBuf = Buffer.from(sig, "hex");
    const expectedBuf = Buffer.from(expectedSig, "hex");
    if (sigBuf.length !== expectedBuf.length) return false;
    if (!timingSafeEqual(sigBuf, expectedBuf)) return false;

    const decoded = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as {
      exp?: number;
    };
    if (typeof decoded.exp !== "number") return false;

    return decoded.exp > Date.now();
  } catch {
    return false;
  }
}
