"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { adminApi } from "@/lib/adminApi";
import { getApiKey } from "@/lib/session";
import AgentSelect from "@/components/AgentSelect";
import type { BatchStats, ClientAgent, ClientSummary, CreateBatchRequest, PhoneNumbersResponse } from "@/lib/types";

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

const SAMPLE_RECIPIENTS = `[
  { "contact_number": "+919876543210", "customer_name": "Asha" },
  { "contact_number": "+919812345678", "customer_name": "Ravi" }
]`;

function pct(v: number) { return `${(v * 100).toFixed(1)}%`; }
function statusClass(s: string | null) {
  if (!s) return "warn";
  if (s === "completed") return "ok";
  if (["failed", "stopped", "deleted"].includes(s)) return "err";
  return "warn";
}

export default function BatchesPage() {
  // Mode detection (runs once on mount)
  const [isAdmin, setIsAdmin] = useState(false);
  const [modeReady, setModeReady] = useState(false);

  useEffect(() => {
    const key = getApiKey() ?? process.env.NEXT_PUBLIC_TURING_API_KEY ?? "";
    setIsAdmin(!key);
    setModeReady(true);
  }, []);

  // Admin: client + agent selection
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [clientId, setClientId] = useState("");
  const [adminAgents, setAdminAgents] = useState<ClientAgent[]>([]);
  const [adminAgentId, setAdminAgentId] = useState("");

  useEffect(() => {
    if (!isAdmin) return;
    adminApi.listClients("active").then(setClients).catch(() => {});
  }, [isAdmin]);

  useEffect(() => {
    setAdminAgents([]);
    setAdminAgentId("");
    setBatches(null);
    if (!clientId) return;
    adminApi.getClientAgents(clientId).then(setAdminAgents).catch(() => {});
  }, [clientId]);

  // Tenant: phone numbers for from-number picker
  const [numbers, setNumbers] = useState<PhoneNumbersResponse | null>(null);
  useEffect(() => {
    if (isAdmin || !modeReady) return;
    api.phoneNumbers().then(setNumbers).catch(() => {});
  }, [isAdmin, modeReady]);

  // Create batch (tenant-only)
  const [agentId, setAgentId] = useState("");
  const [fromNumber, setFromNumber] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [recipients, setRecipients] = useState(SAMPLE_RECIPIENTS);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createResult, setCreateResult] = useState<{ batch_id?: string; state?: string } | null>(null);

  // Quick actions (tenant-only)
  const [scheduleId, setScheduleId] = useState("");
  const [scheduleAt, setScheduleAt] = useState("");
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [actioning, setActioning] = useState(false);

  // Batch list
  const [batches, setBatches] = useState<BatchStats[] | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const loadBatches = useCallback(() => {
    if (!modeReady) return;
    if (isAdmin && !clientId) return;
    setListLoading(true);
    setListError(null);
    const req = isAdmin
      ? adminApi.getClientAnalyticsByBatch(clientId, { agent_id: adminAgentId || undefined })
      : api.analyticsByBatch();
    req
      .then(setBatches)
      .catch((e: unknown) => setListError(e instanceof Error ? e.message : "Failed to load batches"))
      .finally(() => setListLoading(false));
  }, [modeReady, isAdmin, clientId, adminAgentId]);

  useEffect(() => {
    if (!modeReady) return;
    if (isAdmin) return; // admin waits for client selection
    loadBatches();
  }, [modeReady, isAdmin, loadBatches]);

  async function createBatch() {
    setCreateError(null);
    setCreateResult(null);
    let parsed: Record<string, unknown>[];
    try {
      parsed = JSON.parse(recipients);
      if (!Array.isArray(parsed)) throw new Error("must be a JSON array");
    } catch (e) {
      setCreateError(`recipients must be a JSON array: ${e instanceof Error ? e.message : String(e)}`);
      return;
    }
    setCreating(true);
    try {
      const body: CreateBatchRequest = {
        agent_id: agentId.trim(),
        recipients: parsed,
        ...(fromNumber ? { from_phone_numbers: [fromNumber] } : {}),
        ...(webhookUrl ? { webhook_url: webhookUrl.trim() } : {}),
      };
      const res = await api.createBatch(body);
      setCreateResult(res);
      if (res.batch_id) setScheduleId(res.batch_id);
      setTimeout(loadBatches, 800);
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  }

  async function runAction(fn: () => Promise<unknown>, ok: string) {
    setActionMsg(null); setActionErr(null); setActioning(true);
    try { await fn(); setActionMsg(ok); setTimeout(loadBatches, 800); }
    catch (e: unknown) { setActionErr(e instanceof Error ? e.message : String(e)); }
    finally { setActioning(false); }
  }

  const detailHref = (voiceBatchId: string) =>
    isAdmin && clientId
      ? `/batches/${encodeURIComponent(voiceBatchId)}?client=${clientId}`
      : `/batches/${encodeURIComponent(voiceBatchId)}`;

  return (
    <div className="page-enter">
      <h1>Batches</h1>
      <p className="subtitle">Create outbound call batches, schedule them, and view run details.</p>

      {/* Admin: client selector */}
      {modeReady && isAdmin && (
        <div className="card">
          <h2>Select client</h2>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
            <div style={{ flex: "2 1 200px" }}>
              <label>Client</label>
              <select value={clientId} onChange={(e) => setClientId(e.target.value)}>
                <option value="">— Select a client —</option>
                {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div style={{ flex: "2 1 200px" }}>
              <label>Agent</label>
              <select value={adminAgentId} onChange={(e) => setAdminAgentId(e.target.value)} disabled={!clientId}>
                <option value="">All agents</option>
                {adminAgents.filter((a) => a.enabled).map((a) => (
                  <option key={a.voice_agent_id} value={a.voice_agent_id}>
                    {a.display_name || a.agent_name || a.voice_agent_id}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ marginBottom: 14 }}>
              <button onClick={loadBatches} disabled={!clientId || listLoading}>
                {listLoading ? <><span className="spinner" />Loading…</> : "Load batches"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tenant: create batch */}
      {modeReady && !isAdmin && (
        <>
          <div className="card">
            <h2>Create batch</h2>
            {createError && <div className="error-box">{createError}</div>}
            {createResult && (
              <div style={{ background: "rgba(55,201,120,0.10)", border: "1px solid rgba(55,201,120,0.35)", color: "var(--green)", borderRadius: 8, padding: "10px 12px", marginBottom: 14, fontSize: 13 }}>
                Batch created: <strong>{createResult.batch_id}</strong> — state: {createResult.state}
              </div>
            )}
            <div className="row">
              <AgentSelect value={agentId} onChange={setAgentId} />
              <div>
                <label>From (caller ID)</label>
                <select value={fromNumber} onChange={(e) => setFromNumber(e.target.value)}>
                  <option value="">{numbers?.default_from_number ? `Default (${numbers.default_from_number})` : "Account default"}</option>
                  {numbers?.phone_numbers.map((n, i) => (
                    <option key={n.id || i} value={n.phone_number || ""}>{n.phone_number}</option>
                  ))}
                </select>
              </div>
            </div>
            <label>Webhook URL (optional)</label>
            <input value={webhookUrl} onChange={(e) => setWebhookUrl(e.target.value)} placeholder="https://…/webhook" />
            <label>Recipients (JSON array; each needs contact_number)</label>
            <textarea rows={6} value={recipients} onChange={(e) => setRecipients(e.target.value)} />
            <p className="hint">Extra keys become per-recipient prompt variables.</p>
            <button onClick={createBatch} disabled={creating || !agentId}>
              {creating ? <><span className="spinner" />Creating…</> : "Create batch"}
            </button>
          </div>

          <div className="card">
            <h2>Quick actions</h2>
            {actionMsg && <div style={{ background: "rgba(55,201,120,0.10)", border: "1px solid rgba(55,201,120,0.35)", color: "var(--green)", borderRadius: 8, padding: "10px 12px", marginBottom: 14, fontSize: 13 }}>{actionMsg}</div>}
            {actionErr && <div className="error-box">{actionErr}</div>}
            <div className="row">
              <div style={{ flex: "2 1 200px" }}>
                <label>Batch ID</label>
                <input value={scheduleId} onChange={(e) => setScheduleId(e.target.value)} placeholder="batch_id" />
              </div>
              <div style={{ flex: "2 1 200px" }}>
                <label>Schedule at (≥ 2 min out)</label>
                <input type="datetime-local" value={scheduleAt} onChange={(e) => setScheduleAt(e.target.value)} />
              </div>
            </div>
            <div className="btn-row">
              <button disabled={!scheduleId || !scheduleAt || actioning}
                onClick={() => runAction(() => api.scheduleBatch(scheduleId.trim(), toOffsetIso(scheduleAt)), "Batch scheduled.")}>
                Schedule
              </button>
              <button className="danger" disabled={!scheduleId || actioning}
                onClick={() => runAction(() => api.stopBatch(scheduleId.trim()), "Batch stopped.")}>
                Stop
              </button>
              <button className="danger" disabled={!scheduleId || actioning}
                onClick={() => runAction(() => api.deleteBatch(scheduleId.trim()), "Batch deleted.")}>
                Delete
              </button>
            </div>
          </div>
        </>
      )}

      {/* Batch list */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h2 style={{ margin: 0 }}>
            {isAdmin && clientId
              ? `Batches — ${clients.find(c => c.id === clientId)?.name ?? clientId.slice(0, 8)}`
              : "Your batches"}
          </h2>
          <button className="secondary" onClick={loadBatches} disabled={listLoading || (isAdmin && !clientId)}>
            {listLoading ? <><span className="spinner" />Loading…</> : "Refresh"}
          </button>
        </div>

        {isAdmin && !clientId && (
          <div className="empty-state">Select a client above to view their batches.</div>
        )}

        {listError && <div className="error-box">{listError}</div>}

        {listLoading && !batches && (
          <div>
            {[0, 1, 2].map(i => (
              <div key={i} style={{ display: "flex", gap: 12, marginBottom: 12 }}>
                <div className="skeleton skeleton-row" style={{ flex: 2, height: 18 }} />
                <div className="skeleton skeleton-row" style={{ flex: 1, height: 18 }} />
                <div className="skeleton skeleton-row" style={{ flex: 1, height: 18 }} />
              </div>
            ))}
          </div>
        )}

        {batches && batches.length === 0 && (
          <div className="empty-state">No batch runs yet.</div>
        )}

        {batches && batches.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Batch ID</th>
                  <th>Status</th>
                  <th>Total</th>
                  <th>Connected</th>
                  <th>Rate</th>
                  <th>Booking</th>
                  <th>Escalation</th>
                  <th>Scheduled</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {batches.map((b) => (
                  <tr key={b.batch_id}>
                    <td style={{ fontFamily: "ui-monospace, monospace", fontSize: 11 }}>
                      {b.batch_id ? `${b.batch_id.slice(0, 16)}…` : "—"}
                    </td>
                    <td>
                      <span className={`badge ${statusClass(b.batch_status)}`}>{b.batch_status ?? "—"}</span>
                    </td>
                    <td>{b.call_volume.total}</td>
                    <td>{b.call_volume.connected}</td>
                    <td>{pct(b.call_volume.connection_rate)}</td>
                    <td>{b.outcomes.analyzed_count > 0 ? b.outcomes.booking.count : "—"}</td>
                    <td>{b.outcomes.analyzed_count > 0 ? b.outcomes.escalation.count : "—"}</td>
                    <td className="muted" style={{ fontSize: 12 }}>{b.scheduled_at ? b.scheduled_at.slice(0, 16) : "—"}</td>
                    <td>
                      {b.batch_id && (
                        <Link href={detailHref(b.batch_id)}>
                          <button className="secondary" style={{ padding: "4px 10px", fontSize: 12 }}>Details</button>
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
