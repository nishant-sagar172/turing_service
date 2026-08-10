"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { adminApi } from "@/lib/adminApi";
import type {
  AnalyticsOverview,
  BatchSummary,
  CallListItem,
  CallListResponse,
  ClientBatchSummary,
} from "@/lib/types";

const OUTCOME_KEYS = ["booking", "follow_up", "escalation", "not_interested", "no_output", "other"] as const;
const OUTCOME_LABELS: Record<string, string> = {
  booking: "Booking", follow_up: "Follow-up", escalation: "Escalation",
  not_interested: "Not interested", no_output: "No output", other: "Other",
};
const OUTCOME_COLORS: Record<string, string> = {
  booking: "var(--green)", follow_up: "var(--accent)", escalation: "var(--amber)",
  not_interested: "var(--red)", no_output: "var(--muted)", other: "var(--muted)",
};

function pct(v: number) { return `${(v * 100).toFixed(1)}%`; }
function dur(s: number | null) {
  if (s == null) return "—";
  const m = Math.floor(s / 60);
  return m ? `${m}m ${(s % 60).toFixed(0)}s` : `${s.toFixed(1)}s`;
}
function costFmt(v: number | null) { return v == null ? "—" : `$${v.toFixed(4)}`; }
function statusClass(s: string) {
  if (s === "completed") return "ok";
  if (["failed", "stopped", "deleted", "error", "cancelled", "canceled", "busy", "no-answer", "balance-low"].includes(s)) return "err";
  return "warn";
}

function OutcomeBadge({ outcome }: { outcome: string | null }) {
  if (!outcome) return <span className="muted">—</span>;
  const color = OUTCOME_COLORS[outcome] ?? "var(--muted)";
  return (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: 12, fontSize: 11,
      background: `color-mix(in srgb, ${color} 15%, transparent)`,
      border: `1px solid color-mix(in srgb, ${color} 35%, transparent)`,
      color,
    }}>
      {OUTCOME_LABELS[outcome] ?? outcome}
    </span>
  );
}

function AudioPlayer({ url }: { url: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button className="secondary" style={{ padding: "2px 8px", fontSize: 11 }} onClick={() => setOpen(!open)}>
        {open ? "Hide" : "▶ Play"}
      </button>
      {open && (
        <div style={{ marginTop: 6 }}>
          <audio controls src={url} style={{ width: "100%", maxWidth: 320, height: 32 }} />
        </div>
      )}
    </div>
  );
}

const PAGE_SIZE = 50;

function BatchDetailInner() {
  const params = useParams();
  const searchParams = useSearchParams();
  const voiceBatchId = decodeURIComponent(params.id as string);
  const adminClientId = searchParams.get("client"); // present → admin mode
  const isAdmin = !!adminClientId;

  // Batch header — either BatchSummary (tenant) or ClientBatchSummary (admin)
  const [batchSummary, setBatchSummary] = useState<BatchSummary | null>(null);
  const [adminBatch, setAdminBatch] = useState<ClientBatchSummary | null>(null);
  const [internalId, setInternalId] = useState<string | null>(null);

  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [calls, setCalls] = useState<CallListItem[]>([]);
  const [callsTotal, setCallsTotal] = useState(0);
  const [callPage, setCallPage] = useState(1);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (isAdmin && adminClientId) {
        // Admin mode: find batch in the client's batch list by voice_batch_id
        const batchList = await adminApi.listClientBatches(adminClientId);
        const found = batchList.find(b => b.voice_batch_id === voiceBatchId) ?? batchList[0] ?? null;
        setAdminBatch(found);
        const iid = found?.id ?? null;
        setInternalId(iid);

        if (iid) {
          const [ov, callsData] = await Promise.all([
            adminApi.getClientAnalyticsOverview(adminClientId, { batch_id: iid }).catch(() => null),
            adminApi.listClientCalls(adminClientId, { batch_id: iid, page: 1, page_size: PAGE_SIZE }).catch(() => null),
          ]);
          setOverview(ov);
          if (callsData) {
            setCalls(callsData.items ?? []);
            setCallsTotal(callsData.total ?? 0);
          }
        }
      } else {
        // Tenant mode
        const batchData = await api.getBatch(voiceBatchId);
        setBatchSummary(batchData);
        const iid = batchData.internal_id ?? null;
        setInternalId(iid);

        const [metricsData, callsData] = await Promise.all([
          api.getBatchMetrics(voiceBatchId).catch(() => null),
          iid ? api.listCalls({ batch_id: iid, page: 1, page_size: PAGE_SIZE }).catch(() => null) : Promise.resolve(null),
        ]);
        setMetrics(metricsData);
        if (callsData) {
          const r = callsData as CallListResponse;
          setCalls(r.items ?? []);
          setCallsTotal(r.total ?? 0);
        }

        if (iid) {
          const ov = await api.analyticsOverview({ batch_id: iid }).catch(() => null);
          setOverview(ov);
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load batch");
    } finally {
      setLoading(false);
    }
  }, [voiceBatchId, isAdmin, adminClientId]);

  const loadCallsPage = useCallback(async (p: number) => {
    if (!internalId) return;
    const data = isAdmin && adminClientId
      ? await adminApi.listClientCalls(adminClientId, { batch_id: internalId, page: p, page_size: PAGE_SIZE }).catch(() => null)
      : await api.listCalls({ batch_id: internalId, page: p, page_size: PAGE_SIZE }).catch(() => null) as CallListResponse | null;
    if (data) {
      setCalls(data.items ?? []);
      setCallsTotal(data.total ?? 0);
      setCallPage(p);
    }
  }, [internalId, isAdmin, adminClientId]);

  useEffect(() => { load(); }, [load]);

  async function runAction(fn: () => Promise<unknown>, ok: string) {
    setActionMsg(null); setActionErr(null);
    try { await fn(); setActionMsg(ok); load(); }
    catch (e: unknown) { setActionErr(e instanceof Error ? e.message : String(e)); }
  }

  // Unified batch header fields
  const status = batchSummary?.status ?? adminBatch?.status ?? null;
  const agentId = batchSummary?.agent_id ?? adminBatch?.agent_id ?? null;
  const scheduledAt = batchSummary?.scheduled_at ?? adminBatch?.scheduled_at ?? null;
  const createdAt = batchSummary?.created_at ?? adminBatch?.created_at ?? null;
  const totalContacts = batchSummary?.total_contacts ?? adminBatch?.total_count ?? null;
  const validContacts = batchSummary?.valid_contacts ?? null;
  const fromNumbers = batchSummary?.from_phone_numbers ?? null;

  const statusBadgeClass = !status ? "warn" : status === "completed" ? "ok" : ["failed","stopped","deleted"].includes(status) ? "err" : "warn";
  const pages = Math.ceil(callsTotal / PAGE_SIZE);

  const backHref = isAdmin && adminClientId ? `/batches?client=${adminClientId}` : "/batches";

  return (
    <div className="page-enter">
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
        <Link href={backHref}>
          <button className="secondary" style={{ padding: "4px 12px", fontSize: 13 }}>← Batches</button>
        </Link>
        <h1 style={{ margin: 0, fontSize: 22 }}>Batch detail</h1>
        {status && <span className={`badge ${statusBadgeClass}`}>{status}</span>}
      </div>
      <p className="subtitle" style={{ fontFamily: "ui-monospace, monospace", fontSize: 12 }}>{voiceBatchId}</p>

      {error && <div className="error-box">{error}</div>}

      {loading && (
        <div className="card">
          <div className="stat-grid">
            {[0,1,2,3].map(i => (
              <div key={i} className="stat-card">
                <div className="skeleton skeleton-row w-60" style={{ height: 11, marginBottom: 10 }} />
                <div className="skeleton skeleton-row w-40" style={{ height: 26 }} />
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && (batchSummary || adminBatch) && (
        <>
          {/* Summary */}
          <div className="card">
            <h2>Summary</h2>
            <div className="stat-grid">
              {agentId && (
                <div className="stat-card">
                  <div className="stat-label">Agent</div>
                  <div className="stat-value" style={{ fontSize: 12, wordBreak: "break-all" }}>{agentId}</div>
                </div>
              )}
              <div className="stat-card">
                <div className="stat-label">Contacts</div>
                <div className="stat-value">
                  {validContacts != null ? `${validContacts} / ${totalContacts}` : totalContacts ?? "—"}
                </div>
                {validContacts != null && <div className="stat-sub">valid / total</div>}
              </div>
              <div className="stat-card">
                <div className="stat-label">Scheduled</div>
                <div className="stat-value" style={{ fontSize: 13 }}>{scheduledAt ? scheduledAt.slice(0, 16) : "—"}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Created</div>
                <div className="stat-value" style={{ fontSize: 13 }}>
                  {createdAt ? String(createdAt).slice(0, 16) : "—"}
                </div>
              </div>
              {fromNumbers && fromNumbers.length > 0 && (
                <div className="stat-card">
                  <div className="stat-label">From number</div>
                  <div className="stat-value" style={{ fontSize: 13 }}>{fromNumbers[0]}</div>
                </div>
              )}
            </div>

            {actionMsg && <div style={{ background: "rgba(55,201,120,0.10)", border: "1px solid rgba(55,201,120,0.35)", color: "var(--green)", borderRadius: 8, padding: "8px 12px", fontSize: 13, marginTop: 12 }}>{actionMsg}</div>}
            {actionErr && <div className="error-box" style={{ marginTop: 12 }}>{actionErr}</div>}
            {!isAdmin && status && !["completed","deleted"].includes(status) && (
              <div className="btn-row" style={{ marginTop: 16 }}>
                {status !== "stopped" && (
                  <button className="danger" onClick={() => runAction(() => api.stopBatch(voiceBatchId), "Batch stopped.")}>Stop batch</button>
                )}
                <button className="danger" onClick={() => runAction(() => api.deleteBatch(voiceBatchId), "Batch deleted.")}>Delete batch</button>
              </div>
            )}
          </div>

          {/* Execution metrics (tenant only — from Bolna) */}
          {metrics && Object.keys(metrics).length > 0 && (
            <div className="card">
              <h2>Execution metrics</h2>
              <div className="stat-grid">
                {Object.entries(metrics).map(([k, v]) => (
                  <div key={k} className="stat-card">
                    <div className="stat-label">{k.replace(/_/g, " ")}</div>
                    <div className="stat-value" style={{ fontSize: typeof v === "number" && v > 999 ? 16 : 20 }}>
                      {typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(2)) : String(v ?? "—")}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Call volume */}
          {overview && (
            <>
              <div className="card">
                <h2>Call volume</h2>
                <div className="stat-grid">
                  <div className="stat-card">
                    <div className="stat-label">Total</div>
                    <div className="stat-value">{overview.call_volume.total}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Connected</div>
                    <div className="stat-value" style={{ color: "var(--green)" }}>{overview.call_volume.connected}</div>
                    <div className="stat-sub">completed</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Connection rate</div>
                    <div className="stat-value" style={{ color: "var(--green)" }}>{pct(overview.call_volume.connection_rate)}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Not connected</div>
                    <div className="stat-value" style={{ color: "var(--red)" }}>{overview.call_volume.not_connected}</div>
                    <div className="stat-sub">no-answer · busy · failed</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Pending / running</div>
                    <div className="stat-value" style={{ color: overview.call_volume.pending > 0 ? "var(--amber)" : undefined }}>{overview.call_volume.pending}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Avg duration</div>
                    <div className="stat-value">{dur(overview.duration.avg_seconds)}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Total cost</div>
                    <div className="stat-value">{`$${overview.cost.total.toFixed(2)}`}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Avg / connected</div>
                    <div className="stat-value">{costFmt(overview.cost.avg_per_connected)}</div>
                  </div>
                </div>
                {Object.keys(overview.not_connected_breakdown).length > 0 && (
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 8 }}>
                    {Object.entries(overview.not_connected_breakdown).map(([k, v]) => (
                      <span key={k} className="muted" style={{ fontSize: 12 }}>
                        <strong style={{ color: "var(--text)" }}>{v}</strong> {k}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Outcomes */}
              {overview.outcomes.analyzed_count > 0 && (
                <div className="card">
                  <h2>Outcome breakdown</h2>
                  <p className="muted" style={{ fontSize: 12, marginBottom: 16 }}>
                    {overview.outcomes.analyzed_count} analyzed · coverage {pct(overview.outcomes.coverage_pct)} of connected
                  </p>
                  {OUTCOME_KEYS.map((key) => {
                    const entry = overview.outcomes[key];
                    const color = OUTCOME_COLORS[key];
                    return (
                      <div key={key} className="outcome-bar-row">
                        <span style={{ width: 110, fontSize: 12, color: "var(--text)", flexShrink: 0 }}>{OUTCOME_LABELS[key]}</span>
                        <div className="outcome-bar-track">
                          <div className="outcome-bar-fill" style={{ width: pct(entry.pct_of_analyzed), background: color }} />
                        </div>
                        <span style={{ width: 50, fontSize: 12, color, textAlign: "right", flexShrink: 0 }}>{pct(entry.pct_of_analyzed)}</span>
                        <span className="muted" style={{ width: 40, fontSize: 12, textAlign: "right", flexShrink: 0 }}>{entry.count}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}

          {/* Calls table */}
          <div className="card">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <h2 style={{ margin: 0 }}>Calls ({callsTotal})</h2>
              {pages > 1 && (
                <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
                  <button className="secondary" style={{ padding: "3px 10px" }} disabled={callPage <= 1} onClick={() => loadCallsPage(callPage - 1)}>Prev</button>
                  <span className="muted">Page {callPage} / {pages}</span>
                  <button className="secondary" style={{ padding: "3px 10px" }} disabled={callPage >= pages} onClick={() => loadCallsPage(callPage + 1)}>Next</button>
                </div>
              )}
            </div>

            {calls.length === 0 ? (
              <div className="empty-state">No call records yet — webhooks may still be processing.</div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead>
                    <tr>
                      <th>Contact</th>
                      <th>Status</th>
                      <th>Duration</th>
                      <th>Cost</th>
                      <th>Outcome</th>
                      <th>Summary</th>
                      <th>Hangup reason</th>
                      <th>Recording</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {calls.map((c) => (
                      <tr key={c.call_id}>
                        <td style={{ fontFamily: "ui-monospace, monospace", fontSize: 12 }}>{c.contact_number ?? "—"}</td>
                        <td><span className={`badge ${statusClass(c.status)}`}>{c.status}</span></td>
                        <td className="muted">{dur(c.duration)}</td>
                        <td className="muted">{costFmt(c.cost)}</td>
                        <td><OutcomeBadge outcome={c.analysis?.outcome ?? null} /></td>
                        <td style={{ maxWidth: 220, fontSize: 12, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={c.analysis?.summary ?? undefined}>
                          {c.analysis?.summary ?? <span className="muted">—</span>}
                        </td>
                        <td className="muted" style={{ fontSize: 12 }}>{c.hangup_reason ?? "—"}</td>
                        <td>
                          {c.recording_url
                            ? <AudioPlayer url={c.recording_url} />
                            : <span className="muted">—</span>}
                        </td>
                        <td className="muted" style={{ fontSize: 12 }}>{c.created_at.slice(0, 16)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function BatchDetailPage() {
  return (
    <Suspense fallback={<div className="page-enter"><div className="card"><p className="muted">Loading…</p></div></div>}>
      <BatchDetailInner />
    </Suspense>
  );
}
