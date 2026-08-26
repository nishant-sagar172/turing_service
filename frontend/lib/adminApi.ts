// Operator admin API client — calls go through /proxy/admin/* (server-side
// Route Handler that injects X-Admin-Key from process.env.TURING_ADMIN_KEY).
// The browser NEVER holds the admin key.

import { rawReq } from "./http";
import type {
  AgentStats,
  AgentVariables,
  AnalyticsOverview,
  ApproveResult,
  BatchStats,
  CatalogAgent,
  ClientAgent,
  ClientBatchSummary,
  ClientConfig,
  ClientPhoneNumberEntry,
  ClientSummary,
  CallDetail,
  CallListResponse,
  CallAnalysisResult,
  DriftEvent,
  KeySummary,
  PhoneNumberCatalogEntry,
  PhoneNumberSyncResult,
  SyncResult,
  TimeseriesPoint,
  VoiceEngineStatus,
} from "./types";

function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

const BASE = "/proxy/admin";

function req<T>(path: string, opts: { method?: string; body?: string } = {}): Promise<T> {
  return rawReq<T>(`${BASE}${path}`, opts);
}

export const adminApi = {
  // Clients
  createClient: (name: string, contactEmail?: string, status?: string) =>
    req<ClientSummary>("/clients", {
      method: "POST",
      body: JSON.stringify({ name, contact_email: contactEmail ?? null, status: status ?? "pending" }),
    }),
  listClients: (status?: string) =>
    req<ClientSummary[]>(`/clients${status ? `?status=${status}` : ""}`),
  getClient: (id: string) => req<ClientSummary>(`/clients/${id}`),
  updateClient: (id: string, data: { name?: string; contact_email?: string | null }) =>
    req<ClientSummary>(`/clients/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteClient: (id: string) => req<void>(`/clients/${id}`, { method: "DELETE" }),
  approve: (id: string) =>
    req<ApproveResult>(`/clients/${id}/approve`, { method: "POST" }),
  reject: (id: string) =>
    req<ClientSummary>(`/clients/${id}/reject`, { method: "POST" }),
  suspend: (id: string) =>
    req<ClientSummary>(`/clients/${id}/suspend`, { method: "POST" }),
  reactivate: (id: string) =>
    req<ClientSummary>(`/clients/${id}/reactivate`, { method: "POST" }),

  // Keys
  listKeys: (clientId: string) => req<KeySummary[]>(`/clients/${clientId}/keys`),
  issueKey: (clientId: string, label?: string) =>
    req<{ key_id: string; api_key: string }>(`/clients/${clientId}/keys`, {
      method: "POST",
      body: JSON.stringify({ label }),
    }),
  revokeKey: (clientId: string, keyId: string) =>
    req<void>(`/clients/${clientId}/keys/${keyId}`, { method: "DELETE" }),

  // Config
  getConfig: (clientId: string) => req<ClientConfig>(`/clients/${clientId}/config`),
  updateConfig: (clientId: string, data: Partial<ClientConfig>) =>
    req<ClientConfig>(`/clients/${clientId}/config`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // Agents
  listCatalogAgents: () => req<CatalogAgent[]>("/agents"),
  getAgentVariables: (agentId: string) =>
    req<AgentVariables>(`/agents/${agentId}/variables`),
  getClientAgents: (clientId: string) =>
    req<ClientAgent[]>(`/clients/${clientId}/agents`),
  setClientAgents: (clientId: string, voiceAgentIds: string[]) =>
    req<void>(`/clients/${clientId}/agents`, {
      method: "PUT",
      body: JSON.stringify({ voice_agent_ids: voiceAgentIds }),
    }),
  patchClientAgent: (
    clientId: string,
    voiceAgentId: string,
    data: { display_name?: string; variable_overrides?: Record<string, string> }
  ) =>
    req<void>(`/clients/${clientId}/agents/${voiceAgentId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  // Drift
  getDrift: (clientId: string) => req<DriftEvent[]>(`/clients/${clientId}/drift`),
  acknowledgeDrift: (clientId: string, eventId: string) =>
    req<void>(`/clients/${clientId}/drift/${eventId}/acknowledge`, { method: "POST" }),

  // Sync
  syncAgents: () => req<SyncResult>("/agents/sync", { method: "POST" }),
  voiceEngineStatus: () => req<VoiceEngineStatus>("/voice-engine/status"),

  // Phone number catalog
  listPhoneNumberCatalog: () =>
    req<PhoneNumberCatalogEntry[]>("/phone-numbers"),
  syncPhoneNumbers: () =>
    req<PhoneNumberSyncResult>("/phone-numbers/sync", { method: "POST" }),
  getClientPhoneNumbers: (clientId: string) =>
    req<ClientPhoneNumberEntry[]>(`/clients/${clientId}/phone-numbers`),
  setClientPhoneNumbers: (clientId: string, phoneNumberIds: string[]) =>
    req<void>(`/clients/${clientId}/phone-numbers`, {
      method: "PUT",
      body: JSON.stringify({ phone_number_ids: phoneNumberIds }),
    }),

  // Analytics (admin-scoped, per-client)
  getClientAnalyticsOverview: (
    clientId: string,
    params: { date_from?: string; date_to?: string; agent_id?: string; batch_id?: string } = {}
  ) => req<AnalyticsOverview>(`/clients/${clientId}/analytics/overview${qs(params)}`),

  getClientAnalyticsByAgent: (
    clientId: string,
    params: { date_from?: string; date_to?: string; batch_id?: string } = {}
  ) => req<AgentStats[]>(`/clients/${clientId}/analytics/by-agent${qs(params)}`),

  getClientAnalyticsByBatch: (
    clientId: string,
    params: { date_from?: string; date_to?: string; agent_id?: string } = {}
  ) => req<BatchStats[]>(`/clients/${clientId}/analytics/by-batch${qs(params)}`),

  getClientAnalyticsTimeseries: (
    clientId: string,
    params: { date_from?: string; date_to?: string; agent_id?: string; batch_id?: string; granularity?: string } = {}
  ) => req<TimeseriesPoint[]>(`/clients/${clientId}/analytics/timeseries${qs(params)}`),

  // Batches (admin-scoped, per-client)
  listClientBatches: (clientId: string) =>
    req<ClientBatchSummary[]>(`/clients/${clientId}/batches`),

  // Calls (admin-scoped — lists via tenant proxy using admin key aren't available;
  // these hit the admin analytics detail endpoint)
  listClientCalls: (
    clientId: string,
    params: { page?: number; page_size?: number; status?: string; outcome?: string; urgency?: string; q?: string; agent_id?: string; batch_id?: string; date_from?: string; date_to?: string } = {}
  ) => req<CallListResponse>(`/clients/${clientId}/calls${qs(params)}`),

  getClientCallDetail: (clientId: string, callId: string) =>
    req<CallDetail>(`/clients/${clientId}/calls/${callId}`),

  analyzeClientCall: (clientId: string, callId: string) =>
    req<CallAnalysisResult>(`/clients/${clientId}/calls/${callId}/analyze`, { method: "POST" }),
};
