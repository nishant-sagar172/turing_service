// Types mirroring turing_service backend response/request schemas.

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  environment: string;
}

export interface VoiceEngineStatus {
  voice_engine: string;
  base_url: string;
  account?: Record<string, unknown> | null;
  detail?: string | null;
}

// Mirrors app/schemas/agents.py::AgentSummary — the only backend shape this
// type is used for (GET /v1/agents). `id` is always present; the rest are
// genuinely optional on the backend model.
export interface Agent {
  id: string;
  agent_name?: string | null;
  agent_status?: string | null;
  display_name?: string | null;
}

export interface AgentVariables {
  agent_id: string;
  required: string[];
  optional: string[];
  system_injected: string[];
  all_prompt_variables: string[];
}

// Mirrors app/schemas/phone_numbers.py::PhoneNumber — every field is
// genuinely optional on the backend model (extra="allow" preserves any
// additional Bolna fields at runtime, but nothing in the frontend reads them
// by name, so there is no typed field to add here).
export interface PhoneNumber {
  id?: string | null;
  phone_number?: string | null;
  agent_id?: string | null;
  telephony_provider?: string | null;
  rented?: boolean | null;
  price?: string | null;
  renewal_at?: string | null;
}

export interface PhoneNumbersResponse {
  default_from_number?: string | null;
  phone_numbers: PhoneNumber[];
}

export interface MakeCallRequest {
  agent_id: string;
  recipient_phone_number: string;
  from_phone_number?: string;
  user_data?: Record<string, unknown>;
  scheduled_at?: string;
}

export interface MakeCallResponse {
  message?: string;
  status?: string;
  execution_id?: string;
}

// Mirrors app/schemas/calls.py::ExecutionResponse — every field is genuinely
// optional on the backend model (extra="allow" preserves any additional
// Bolna fields at runtime; the frontend only reads the named fields below).
export interface Execution {
  id?: string | null;
  agent_id?: string | null;
  status?: string | null;
  conversation_duration?: number | null;
  total_cost?: number | null;
  transcript?: string | null;
  extracted_data?: Record<string, unknown> | null;
  telephony_data?: Record<string, unknown> | null;
  error_message?: string | null;
}

export interface CreateBatchRequest {
  agent_id: string;
  recipients: Record<string, unknown>[];
  from_phone_numbers?: string[];
  webhook_url?: string;
}

export interface BatchCreateResponse {
  batch_id?: string;
  state?: string;
}

export interface ScheduleBatchResponse {
  message?: string;
  state?: string;
}

// Mirrors app/schemas/batches.py::BatchSummary — every field is genuinely
// optional on the backend model (extra="allow" preserves any additional
// Bolna fields at runtime; the frontend only reads the named fields below).
export interface BatchSummary {
  batch_id?: string | null;
  internal_id?: string | null;
  status?: string | null;
  scheduled_at?: string | null;
  file_name?: string | null;
  valid_contacts?: number | null;
  total_contacts?: number | null;
  from_phone_numbers?: string[] | null;
  execution_status?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
  agent_id?: string | null;
}

// ── Admin types ──────────────────────────────────────────────────────────────

export interface ClientSummary {
  id: string;
  name: string;
  slug: string;
  contact_email?: string | null;
  status: string;
  created_at: string;
  approved_at?: string | null;
}

export interface KeySummary {
  id: string;
  key_prefix: string;
  label?: string | null;
  status: string;
  last_used_at?: string | null;
  expires_at?: string | null;
  created_at: string;
}

export interface ClientConfig {
  default_from_number?: string | null;
  webhook_url?: string | null;
  webhook_secret_set?: boolean;
  visible_fields?: Record<string, unknown> | null;
  settings?: Record<string, unknown> | null;
  analysis_llm_provider?: string | null;
  analysis_llm_model?: string | null;
  analysis_prompt_hint?: string | null;
  analysis_llm_api_key_set?: boolean;
  analysis_llm_api_key?: string | null;
}

export interface CatalogAgent {
  voice_agent_id: string;
  agent_name?: string | null;
  agent_status?: string | null;
  is_present: boolean;
  last_synced_at?: string | null;
}

export interface ClientAgent {
  voice_agent_id: string;
  enabled: boolean;
  display_name?: string | null;
  variable_overrides?: Record<string, string> | null;
  agent_name?: string | null;
  is_present?: boolean | null;
}

export interface DriftEvent {
  id: string;
  voice_agent_id: string;
  event_type: string;
  detail?: Record<string, unknown> | null;
  acknowledged: boolean;
  created_at: string;
}

export interface PhoneNumberCatalogEntry {
  id: string;
  phone_number: string;
  telephony_provider?: string | null;
  rented?: boolean | null;
  renewal_at?: string | null;
  is_present: boolean;
  last_synced_at?: string | null;
}

export interface ClientPhoneNumberEntry {
  id: string;
  phone_number: string;
  telephony_provider?: string | null;
  rented?: boolean | null;
  is_present: boolean;
}

export interface PhoneNumberSyncResult {
  synced: number;
  removed: number;
}

export interface ApproveResult {
  client_id: string;
  status: string;
  api_key: string;
  claim_url?: string | null;
}

export interface SyncResult {
  synced: number;
  removed: number;
  drift_events: number;
}

// Mirrors app/schemas/batches.py::BatchMetricsResponse (GET /v1/batches/{id}/metrics).
// No extra="allow" on the backend model, so every field below is exactly
// what the endpoint returns — no index signature needed.
export interface BatchMetrics {
  batch_id: string;
  voice_batch_id: string | null;
  status: string;
  total_recipients: number;
  calls_tracked: number;
  by_status: Record<string, number>;
  completed: number;
  terminal: number;
  success_rate: number | null;
  total_cost: number;
  avg_duration_seconds: number | null;
}

export interface ClientBatchSummary {
  id: string;
  voice_batch_id: string | null;
  agent_id: string;
  status: string;
  total_count: number;
  scheduled_at: string | null;
  created_at: string;
}

// ── Portal (me) types ────────────────────────────────────────────────────────

export interface MeResponse {
  client_id: string;
  name: string;
  slug: string;
  contact_email?: string | null;
  status: string;
  created_at: string;
  approved_at?: string | null;
  active_key_count: number;
}

// ── Analysis types ────────────────────────────────────────────────────────────

export interface CallAnalysisResult {
  outcome: string;
  summary: string | null;
  reason: string | null;
  requests: string[];
  urgency: string | null;
  confidence: number | null;
  symptoms_reported: string[] | null;
  model_used: string | null;
  analyzed_at: string | null;
}

export interface CallListItem {
  call_id: string;
  agent_id: string | null;
  batch_id: string | null;
  contact_number: string | null;
  from_number: string | null;
  status: string;
  duration: number | null;
  cost: number | null;
  hangup_reason: string | null;
  recording_url: string | null;
  created_at: string;
  analysis: CallAnalysisResult | null;
}

export interface CallDetail extends CallListItem {
  transcript: string | null;
  extracted_data: Record<string, unknown> | null;
  patient_ref: string | null;
  retry_count: number;
}

export interface CallListResponse {
  items: CallListItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// ── Analytics types ───────────────────────────────────────────────────────────

export interface CallVolumeStats {
  total: number;
  connected: number;
  not_connected: number;
  pending: number;
  connection_rate: number;
}

export interface DurationStats {
  total_seconds: number;
  avg_seconds: number | null;
  p50_seconds: number | null;
  p90_seconds: number | null;
}

export interface CostStats {
  total: number;
  avg_per_call: number | null;
  avg_per_connected: number | null;
}

export interface OutcomeCount {
  count: number;
  pct_of_analyzed: number;
}

export interface OutcomeBreakdown {
  analyzed_count: number;
  coverage_pct: number;
  booking: OutcomeCount;
  escalation: OutcomeCount;
  not_interested: OutcomeCount;
  no_output: OutcomeCount;
  follow_up: OutcomeCount;
  other: OutcomeCount;
  not_reached: OutcomeCount;
}

export interface RetryStats {
  calls_with_retry: number;
  avg_retries: number | null;
}

export interface AnalyticsPeriod {
  from: string | null;
  to: string | null;
}

export interface AnalyticsOverview {
  period: AnalyticsPeriod;
  call_volume: CallVolumeStats;
  duration: DurationStats;
  cost: CostStats;
  outcomes: OutcomeBreakdown;
  not_connected_breakdown: Record<string, number>;
  retry_stats: RetryStats;
}

export interface AgentStats {
  agent_id: string;
  call_volume: CallVolumeStats;
  duration: DurationStats;
  cost: CostStats;
  outcomes: OutcomeBreakdown;
}

export interface BatchStats {
  batch_id: string;
  batch_status: string | null;
  scheduled_at: string | null;
  total_recipients: number | null;
  call_volume: CallVolumeStats;
  duration: DurationStats;
  cost: CostStats;
  outcomes: OutcomeBreakdown;
}

export interface TimeseriesPoint {
  date: string;
  total: number;
  connected: number;
  not_connected: number;
  outcomes: Record<string, number>;
}

// ── Claim / registration types ───────────────────────────────────────────────

export interface ClaimPeek {
  client_name: string;
  expires_in_seconds: number;
}

export interface ClaimResult {
  client_name: string;
  api_key: string;
}

export interface RegisterResult {
  status: string;
  message: string;
}
