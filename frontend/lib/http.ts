// Raw fetch helper — no auth headers. Used by api.ts, adminApi.ts, publicApi.ts.

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export async function rawReq<T>(
  url: string,
  opts: RequestInit & { headers?: Record<string, string> } = {}
): Promise<T> {
  const res = await fetch(url, {
    ...opts,
    headers: {
      ...(opts.body && !(opts.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...(opts.headers || {}),
    },
    cache: "no-store",
  });

  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!res.ok) {
    const d = data as { message?: string; detail?: unknown } | null;
    const msg =
      (d && (d.message || (typeof d.detail === "string" ? d.detail : null))) ||
      `Request failed (${res.status})`;
    throw new ApiError(msg, res.status, data);
  }
  return data as T;
}
