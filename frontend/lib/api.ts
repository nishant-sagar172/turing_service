// Tenant API client — all calls go through /api/* (Next rewrite → backend).
// Reads the API key from sessionStorage at call time (portal sign-in flow).
// Falls back to NEXT_PUBLIC_TURING_API_KEY for local dev convenience.

import { rawReq } from "./http";
import { getApiKey } from "./session";
import type {
  Agent,
  AgentVariables,
  AnalyticsOverview,
  AgentStats,
  BatchStats,
  BatchCreateResponse,
  BatchSummary,
  CallAnalysisResult,
  CallDetail,
  CallListResponse,
  CreateBatchRequest,
  Execution,
  HealthResponse,
  KeySummary,
  MakeCallRequest,
  MakeCallResponse,
  MeResponse,
  PhoneNumbersResponse,
  ScheduleBatchResponse,
  TimeseriesPoint,
} from "./types";

function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

const BASE = "/api";

function req<T>(path: string, opts: { method?: string; body?: string } = {}): Promise<T> {
  const key = getApiKey() ?? process.env.NEXT_PUBLIC_TURING_API_KEY ?? "";
  return rawReq<T>(`${BASE}${path}`, {
    ...opts,
    headers: { "X-API-Key": key },
  });
}

export const api = {
  health: () => req<HealthResponse>("/health"),
  phoneNumbers: () => req<PhoneNumbersResponse>("/v1/phone-numbers"),
  agents: () => req<Agent[]>("/v1/agents"),
  agentVariables: (id: string) => req<AgentVariables>(`/v1/agents/${id}/variables`),

  makeCall: (body: MakeCallRequest) =>
    req<MakeCallResponse>("/v1/calls", { method: "POST", body: JSON.stringify(body) }),
  getCall: (id: string) => req<Execution>(`/v1/calls/${id}`),
  stopCall: (id: string) =>
    req<MakeCallResponse>(`/v1/calls/${id}/stop`, { method: "POST" }),

  createBatch: (body: CreateBatchRequest) =>
    req<BatchCreateResponse>("/v1/batches", { method: "POST", body: JSON.stringify(body) }),
  scheduleBatch: (id: string, scheduled_at: string) =>
    req<ScheduleBatchResponse>(`/v1/batches/${id}/schedule`, {
      method: "POST",
      body: JSON.stringify({ scheduled_at }),
    }),
  listAgentBatches: (agentId: string) => req<BatchSummary[]>(`/v1/batches/by-agent/${agentId}`),
  getBatch: (id: string) => req<BatchSummary>(`/v1/batches/${id}`),
  getBatchExecutions: (id: string) => req<Execution[]>(`/v1/batches/${id}/executions`),
  getBatchMetrics: (id: string) => req<Record<string, unknown>>(`/v1/batches/${id}/metrics`),
  stopBatch: (id: string) =>
    req<{ message?: string; state?: string }>(`/v1/batches/${id}/stop`, { method: "POST" }),
  deleteBatch: (id: string) =>
    req<{ message?: string; state?: string }>(`/v1/batches/${id}`, { method: "DELETE" }),

  // Call records (paginated list + detail + on-demand analysis)
  listCalls: (params: { page?: number; page_size?: number; status?: string; outcome?: string; urgency?: string; q?: string; agent_id?: string; batch_id?: string; date_from?: string; date_to?: string } = {}) =>
    req<CallListResponse>(`/v1/calls${qs(params)}`),
  getCallDetail: (id: string) => req<CallDetail>(`/v1/calls/${id}`),
  analyzeCall: (id: string) =>
    req<CallAnalysisResult>(`/v1/calls/${id}/analyze`, { method: "POST" }),

  // Analytics (tenant-scoped)
  analyticsOverview: (params: { date_from?: string; date_to?: string; agent_id?: string; batch_id?: string } = {}) =>
    req<AnalyticsOverview>(`/v1/analytics/overview${qs(params)}`),
  analyticsByAgent: (params: { date_from?: string; date_to?: string; batch_id?: string } = {}) =>
    req<AgentStats[]>(`/v1/analytics/by-agent${qs(params)}`),
  analyticsByBatch: (params: { date_from?: string; date_to?: string; agent_id?: string } = {}) =>
    req<BatchStats[]>(`/v1/analytics/by-batch${qs(params)}`),
  analyticsTimeseries: (params: { date_from?: string; date_to?: string; granularity?: string } = {}) =>
    req<TimeseriesPoint[]>(`/v1/analytics/timeseries${qs(params)}`),

  // Self-serve portal (me)
  me: () => req<MeResponse>("/v1/me"),
  myKeys: () => req<KeySummary[]>("/v1/me/keys"),
  issueMyKey: (label?: string) =>
    req<{ key_id: string; api_key: string }>("/v1/me/keys", {
      method: "POST",
      body: JSON.stringify({ label }),
    }),
  revokeMyKey: (keyId: string) =>
    req<void>(`/v1/me/keys/${keyId}`, { method: "DELETE" }),
};
