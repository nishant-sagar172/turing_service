// Public (unauthenticated) API calls — registration and claim links.

import { rawReq } from "./http";
import type { ClaimPeek, ClaimResult, RegisterResult } from "./types";

const BASE = "/api/v1";

export const publicApi = {
  register: (name: string, contactEmail?: string) =>
    rawReq<RegisterResult>(`${BASE}/register`, {
      method: "POST",
      body: JSON.stringify({ name, contact_email: contactEmail }),
    }),

  claimPeek: (token: string) =>
    rawReq<ClaimPeek>(`${BASE}/claim/${token}`),

  claimBurn: (token: string) =>
    rawReq<ClaimResult>(`${BASE}/claim/${token}`, { method: "POST" }),
};
