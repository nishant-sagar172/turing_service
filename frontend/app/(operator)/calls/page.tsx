"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { adminApi } from "@/lib/adminApi";
import AgentSelect from "@/components/AgentSelect";
import CallDetailDrawer from "@/components/CallDetailDrawer";
import { getApiKey } from "@/lib/session";
import type {
  AgentVariables,
  CallListItem,
  CallListResponse,
  ClientAgent,
  ClientSummary,
  Execution,
  PhoneNumbersResponse,
} from "@/lib/types";

const OUTCOME_COLORS: Record<string, string> = {
  booking: "var(--green)",
  escalation: "var(--amber)",
  not_interested: "var(--red)",
  no_output: "var(--muted)",
  follow_up: "var(--accent)",
  other: "var(--muted)",
  not_reached: "var(--muted)",
};

function OutcomeBadge({ outcome }: { outcome: string }) {
  const color = OUTCOME_COLORS[outcome] ?? "var(--muted)";
  return (
    <span style={{
      fontSize: 11, padding: "2px 8px", borderRadius: 20, fontWeight: 600,
      background: `color-mix(in srgb, ${color} 14%, transparent)`,
      border: `1px solid color-mix(in srgb, ${color} 35%, transparent)`,
      color,
      whiteSpace: "nowrap",
    }}>
      {outcome.replace("_", " ")}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cls = status === "completed" ? "ok" : status === "failed" || status === "error" ? "err" : "warn";
  return <span className={`badge ${cls}`}>{status}</span>;
}

// ── Call Records Panel ────────────────────────────────────────────────────────

const STATUSES = ["", "completed", "failed", "no-answer", "busy", "cancelled", "stopped", "error"];

function CallRecordsPanel({ clientId }: { clientId: string }) {
  const [data, setData] = useState<CallListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    adminApi.listClientCalls(clientId, { page, page_size: 20, status: status || undefined, date_from: dateFrom || undefined, date_to: dateTo || undefined })
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [clientId, page, status, dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  function applyFilters() { setPage(1); load(); }

  return (
    <div className="card">
      <h2>Call Records</h2>

      {/* Filters */}
      <div className="row" style={{ marginBottom: 14 }}>
        <div>
          <label>Status</label>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s || "All statuses"}</option>)}
          </select>
        </div>
        <div>
          <label>From</label>
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div>
          <label>To</label>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
        <div>
          <label style={{ visibility: "hidden" }}>Filter</label>
          <button className="secondary" style={{ width: "100%" }} onClick={applyFilters}>Filter</button>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Contact</th>
              <th>Status</th>
              <th>Agent</th>
              <th>Duration</th>
              <th>Cost</th>
              <th>Outcome</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              [0,1,2,3].map((i) => (
                <tr key={i}>
                  {[60,40,50,30,30,50,60,30].map((w, j) => (
                    <td key={j}><div className={`skeleton skeleton-row w-${w}`} style={{ height: 12, margin: 0 }} /></td>
                  ))}
                </tr>
              ))
            )}
            {!loading && data?.items.length === 0 && (
              <tr><td colSpan={8} className="muted" style={{ textAlign: "center", padding: 24 }}>No calls found.</td></tr>
            )}
            {!loading && data?.items.map((call: CallListItem) => (
              <tr key={call.call_id}>
                <td style={{ fontFamily: "ui-monospace, monospace", fontSize: 12 }}>{call.contact_number ?? "—"}</td>
                <td><StatusBadge status={call.status} /></td>
                <td className="muted" style={{ fontSize: 12, maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{call.agent_id ?? "—"}</td>
                <td className="muted">{call.duration != null ? `${call.duration.toFixed(1)}s` : "—"}</td>
                <td className="muted">{call.cost != null ? `$${call.cost.toFixed(4)}` : "—"}</td>
                <td>{call.analysis ? <OutcomeBadge outcome={call.analysis.outcome} /> : <span className="muted" style={{ fontSize: 12 }}>—</span>}</td>
                <td className="muted" style={{ fontSize: 12 }}>{new Date(call.created_at).toLocaleDateString()}</td>
                <td>
                  <button className="secondary" style={{ fontSize: 12, padding: "3px 10px" }}
                    onClick={() => setSelectedId(call.call_id)}>
                    Detail
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 16, justifyContent: "flex-end" }}>
          <button className="secondary" style={{ fontSize: 12, padding: "4px 12px" }}
            disabled={page === 1} onClick={() => setPage((p) => p - 1)}>← Prev</button>
          <span className="muted" style={{ fontSize: 13 }}>Page {page} / {data.pages} ({data.total} calls)</span>
          <button className="secondary" style={{ fontSize: 12, padding: "4px 12px" }}
            disabled={page === data.pages} onClick={() => setPage((p) => p + 1)}>Next →</button>
        </div>
      )}

      {selectedId && <CallDetailDrawer mode="admin" clientId={clientId} callId={selectedId} onClose={() => setSelectedId(null)} />}
    </div>
  );
}

function toOffsetIso(local: string): string {
  const d = new Date(local);
  const pad = (n: number) => String(Math.abs(n)).padStart(2, "0");
  const tz = -d.getTimezoneOffset();
  const sign = tz >= 0 ? "+" : "-";
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}` +
    `${sign}${pad(Math.floor(Math.abs(tz) / 60))}:${pad(Math.abs(tz) % 60)}`
  );
}

export default function CallsPage() {
  const [isAdmin, setIsAdmin] = useState(false);
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [clientId, setClientId] = useState("");
  const [clientAgents, setClientAgents] = useState<ClientAgent[]>([]);

  useEffect(() => {
    const key = getApiKey() ?? process.env.NEXT_PUBLIC_TURING_API_KEY ?? "";
    setIsAdmin(!key);
  }, []);

  useEffect(() => {
    adminApi.listClients().then((list) => {
      const active = list.filter((c) => c.status === "active");
      setClients(active);
      if (active.length > 0) setClientId(active[0].id);
    }).catch(() => {});
  }, []);

  const [numbers, setNumbers] = useState<PhoneNumbersResponse | null>(null);
  const [agentId, setAgentId] = useState("");

  useEffect(() => {
    setClientAgents([]);
    setAgentId("");
    if (!clientId) return;
    adminApi.getClientAgents(clientId)
      .then((agents) => setClientAgents(agents.filter((a) => a.enabled)))
      .catch(() => {});
  }, [clientId]);
  const [recipient, setRecipient] = useState("");
  const [fromNumber, setFromNumber] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");

  const [vars, setVars] = useState<AgentVariables | null>(null);
  const [varValues, setVarValues] = useState<Record<string, string>>({});
  const [varsLoading, setVarsLoading] = useState(false);
  const [varsError, setVarsError] = useState<string | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const [trackId, setTrackId] = useState("");
  const [execution, setExecution] = useState<Execution | null>(null);
  const [trackError, setTrackError] = useState<string | null>(null);
  const [tracking, setTracking] = useState(false);

  useEffect(() => {
    api.phoneNumbers().then(setNumbers).catch(() => setNumbers(null));
  }, []);

  useEffect(() => {
    setVars(null);
    setVarValues({});
    setVarsError(null);
    if (!agentId) return;
    setVarsLoading(true);
    const req = isAdmin
      ? adminApi.getAgentVariables(agentId)
      : api.agentVariables(agentId);
    req
      .then((v) => setVars(v))
      .catch((e) => setVarsError(e instanceof Error ? e.message : String(e)))
      .finally(() => setVarsLoading(false));
  }, [agentId, isAdmin]);

  const missingRequired = vars
    ? vars.required.filter((k) => !(varValues[k] ?? "").trim())
    : [];

  function buildUserData(): Record<string, string> | undefined {
    if (!vars) return undefined;
    const data: Record<string, string> = {};
    for (const k of vars.required) data[k] = (varValues[k] ?? "").trim();
    for (const k of vars.optional) {
      const val = (varValues[k] ?? "").trim();
      if (val) data[k] = val;
    }
    return Object.keys(data).length ? data : undefined;
  }

  async function submit() {
    setError(null);
    setResult(null);
    setSubmitting(true);
    try {
      const userData = buildUserData();
      const res = await api.makeCall({
        agent_id: agentId.trim(),
        recipient_phone_number: recipient.trim(),
        ...(fromNumber ? { from_phone_number: fromNumber } : {}),
        ...(userData ? { user_data: userData } : {}),
        ...(scheduledAt ? { scheduled_at: toOffsetIso(scheduledAt) } : {}),
      });
      setResult(res as Record<string, unknown>);
      if (res.execution_id) setTrackId(res.execution_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function track() {
    setTrackError(null);
    setExecution(null);
    setTracking(true);
    try {
      setExecution(await api.getCall(trackId.trim()));
    } catch (e) {
      setTrackError(e instanceof Error ? e.message : String(e));
    } finally {
      setTracking(false);
    }
  }

  async function stop() {
    setTrackError(null);
    try {
      await api.stopCall(trackId.trim());
      await track();
    } catch (e) {
      setTrackError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="page-enter">
      <h1>Calls</h1>
      <p className="subtitle">Trigger a single outbound call, track it, or browse call records.</p>

      <div style={{ marginBottom: 20 }}>
        <label>Client</label>
        <select value={clientId} onChange={(e) => setClientId(e.target.value)} style={{ marginLeft: 10 }}>
          {clients.length === 0 && <option value="">No active clients</option>}
          {clients.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      </div>

      <div className="card">
        <h2>Make a call</h2>
        {error && <div className="error-box">{error}</div>}

        <div className="row">
          {isAdmin ? (
            <div>
              <label>Agent</label>
              <select value={agentId} onChange={(e) => setAgentId(e.target.value)} disabled={!clientId}>
                <option value="">{clientId ? "Select an agent…" : "Select a client first"}</option>
                {clientAgents.map((a) => (
                  <option key={a.voice_agent_id} value={a.voice_agent_id}>
                    {a.display_name || a.agent_name || a.voice_agent_id}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <AgentSelect value={agentId} onChange={setAgentId} />
          )}
          <div>
            <label>Recipient phone number</label>
            <input
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              placeholder="+919876543210"
            />
          </div>
        </div>

        <div className="row">
          <div>
            <label>From (caller ID)</label>
            <select value={fromNumber} onChange={(e) => setFromNumber(e.target.value)}>
              <option value="">
                {numbers?.default_from_number
                  ? `Default (${numbers.default_from_number})`
                  : "Backend / account default"}
              </option>
              {numbers?.phone_numbers.map((n, i) => (
                <option key={n.id || i} value={n.phone_number || ""}>
                  {n.phone_number}
                  {n.telephony_provider ? ` · ${n.telephony_provider}` : ""}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label>Schedule at (optional)</label>
            <input
              type="datetime-local"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
            />
          </div>
        </div>

        <label>Agent variables</label>
        {!agentId ? (
          <p className="hint">Select an agent to load its variables.</p>
        ) : varsLoading ? (
          <p className="hint"><span className="spinner" />Loading agent variables…</p>
        ) : varsError ? (
          <div className="error-box">{varsError}</div>
        ) : vars && vars.all_prompt_variables.length === 0 ? (
          <p className="hint">This agent&apos;s prompt references no variables — nothing to fill in.</p>
        ) : vars ? (
          <>
            {vars.required.map((name) => (
              <div key={name}>
                <label>
                  {name} <span style={{ color: "var(--red)" }}>*</span>
                </label>
                <input
                  value={varValues[name] ?? ""}
                  onChange={(e) => setVarValues((v) => ({ ...v, [name]: e.target.value }))}
                  placeholder={`required · {${name}}`}
                />
              </div>
            ))}
            {vars.optional.map((name) => (
              <div key={name}>
                <label>{name} (optional)</label>
                <input
                  value={varValues[name] ?? ""}
                  onChange={(e) => setVarValues((v) => ({ ...v, [name]: e.target.value }))}
                  placeholder={`optional · {${name}}`}
                />
              </div>
            ))}
            <p className="hint">
              System variables (auto-injected): {vars.system_injected.join(", ")}.
            </p>
          </>
        ) : null}

        <button
          onClick={submit}
          disabled={submitting || !agentId || !recipient || missingRequired.length > 0}
        >
          {submitting ? (
            <><span className="spinner" />Placing…</>
          ) : missingRequired.length ? (
            `Fill required: ${missingRequired.join(", ")}`
          ) : (
            "Place call"
          )}
        </button>

        {result && <pre style={{ marginTop: 16 }}>{JSON.stringify(result, null, 2)}</pre>}
      </div>

      {clientId && <CallRecordsPanel clientId={clientId} />}

      <div className="card">
        <h2>Track a call</h2>
        {trackError && <div className="error-box">{trackError}</div>}
        <label>Execution ID</label>
        <input
          value={trackId}
          onChange={(e) => setTrackId(e.target.value)}
          placeholder="execution_id from a placed call"
        />
        <div className="btn-row">
          <button onClick={track} disabled={tracking || !trackId}>
            {tracking ? <><span className="spinner" />Fetching…</> : "Fetch status"}
          </button>
          <button className="danger" onClick={stop} disabled={!trackId}>
            Stop call
          </button>
        </div>

        {execution && (
          <div style={{ marginTop: 16, animation: "page-in 0.3s var(--ease-glass)" }}>
            <p style={{ marginTop: 0 }}>
              Status:{" "}
              <span className={`badge ${execution.status === "completed" ? "ok" : execution.status === "failed" ? "err" : "warn"}`}>
                {execution.status}
              </span>
            </p>
            {execution.transcript && (
              <>
                <label>Transcript</label>
                <pre>{execution.transcript}</pre>
              </>
            )}
            <label style={{ marginTop: 12 }}>Full execution</label>
            <pre>{JSON.stringify(execution, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  );
}
