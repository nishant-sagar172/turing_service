"use client";

import { useEffect, useState, useCallback } from "react";
import { adminApi } from "@/lib/adminApi";
import type {
  AgentStats,
  AnalyticsOverview,
  BatchStats,
  ClientAgent,
  ClientBatchSummary,
  ClientSummary,
  TimeseriesPoint,
} from "@/lib/types";

const OUTCOME_KEYS = ["booking", "follow_up", "escalation", "not_interested", "no_output", "other", "not_reached"] as const;
const OUTCOME_LABELS: Record<string, string> = {
  booking: "Booking",
  follow_up: "Follow-up",
  escalation: "Escalation",
  not_interested: "Not interested",
  no_output: "No output",
  other: "Other",
  not_reached: "Not reached",
};
const OUTCOME_COLORS: Record<string, string> = {
  booking: "var(--green)",
  follow_up: "var(--accent)",
  escalation: "var(--amber)",
  not_interested: "var(--red)",
  no_output: "var(--muted)",
  other: "var(--muted)",
  not_reached: "var(--muted)",
};

function pct(v: number) { return `${(v * 100).toFixed(1)}%`; }
function dur(s: number | null) { if (s == null) return "—"; const m = Math.floor(s / 60); return m ? `${m}m ${(s % 60).toFixed(0)}s` : `${s.toFixed(1)}s`; }
function cost(v: number | null) { if (v == null) return "—"; return `$${v.toFixed(4)}`; }

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={color ? { color } : undefined}>{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

// ── Outcome bars ──────────────────────────────────────────────────────────────

function OutcomeBars({ overview }: { overview: AnalyticsOverview }) {
  const { outcomes } = overview;
  if (outcomes.analyzed_count === 0) {
    return <p className="muted" style={{ fontSize: 13 }}>No analyzed calls in this period.</p>;
  }
  return (
    <div>
      {OUTCOME_KEYS.map((key) => {
        const entry = outcomes[key];
        const color = OUTCOME_COLORS[key];
        return (
          <div key={key} className="outcome-bar-row">
            <span style={{ width: 110, fontSize: 12, color: "var(--text)", flexShrink: 0 }}>{OUTCOME_LABELS[key]}</span>
            <div className="outcome-bar-track">
              <div
                className="outcome-bar-fill"
                style={{ width: pct(entry.pct_of_analyzed), background: color }}
              />
            </div>
            <span style={{ width: 50, fontSize: 12, color, textAlign: "right", flexShrink: 0 }}>{pct(entry.pct_of_analyzed)}</span>
            <span className="muted" style={{ width: 40, fontSize: 12, textAlign: "right", flexShrink: 0 }}>{entry.count}</span>
          </div>
        );
      })}
      <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
        {outcomes.analyzed_count} analyzed · coverage {pct(outcomes.coverage_pct)} of terminal calls
      </p>
    </div>
  );
}

// ── Timeseries bar chart ──────────────────────────────────────────────────────

function TimeseriesChart({ points }: { points: TimeseriesPoint[] }) {
  if (points.length === 0) return <p className="muted" style={{ fontSize: 13 }}>No data for this period.</p>;

  const maxTotal = Math.max(...points.map((p) => p.total), 1);
  const barW = Math.max(8, Math.min(36, Math.floor(560 / points.length) - 4));
  const chartH = 120;

  return (
    <div style={{ overflowX: "auto" }}>
      <svg
        viewBox={`0 0 ${Math.max(560, points.length * (barW + 4))} 148`}
        style={{ width: "100%", height: 148, display: "block" }}
        aria-label="Call volume timeseries"
      >
        {points.map((p, i) => {
          const totalH = (p.total / maxTotal) * chartH;
          const connH = (p.connected / maxTotal) * chartH;
          const ncH = ((p.not_connected ?? 0) / maxTotal) * chartH;
          const x = i * (barW + 4);
          return (
            <g key={p.date}>
              {/* total bar (faint background) */}
              <rect x={x} y={chartH - totalH} width={barW} height={totalH}
                fill="rgba(79,140,255,0.13)" rx={3} />
              {/* not-connected bar (red, anchored to bottom) */}
              <rect x={x} y={chartH - ncH} width={barW} height={ncH}
                fill="rgba(239,68,68,0.55)" rx={3} />
              {/* connected bar (blue, stacked above not-connected) */}
              <rect x={x} y={chartH - ncH - connH} width={barW} height={connH}
                fill="rgba(79,140,255,0.75)" rx={3} />
              {(i === 0 || i === points.length - 1 || (points.length > 6 && i % Math.ceil(points.length / 6) === 0)) && (
                <text x={x + barW / 2} y={chartH + 14} textAnchor="middle" fontSize={9} fill="var(--muted)">
                  {p.date.slice(5)}
                </text>
              )}
            </g>
          );
        })}
        {/* legend */}
        <rect x={0} y={chartH + 22} width={10} height={8} fill="rgba(79,140,255,0.75)" rx={2} />
        <text x={14} y={chartH + 30} fontSize={9} fill="var(--muted)">Connected</text>
        <rect x={72} y={chartH + 22} width={10} height={8} fill="rgba(239,68,68,0.55)" rx={2} />
        <text x={86} y={chartH + 30} fontSize={9} fill="var(--muted)">Not connected</text>
        <rect x={168} y={chartH + 22} width={10} height={8} fill="rgba(79,140,255,0.13)" rx={2} />
        <text x={182} y={chartH + 30} fontSize={9} fill="var(--muted)">Total</text>
      </svg>
    </div>
  );
}

// ── By-agent table ────────────────────────────────────────────────────────────

function AgentTable({ rows }: { rows: AgentStats[] }) {
  if (rows.length === 0) return <p className="muted" style={{ fontSize: 13 }}>No data.</p>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table>
        <thead>
          <tr>
            <th>Agent</th>
            <th>Total</th>
            <th>Connected</th>
            <th>Conn. rate</th>
            <th>Not conn.</th>
            <th>NC rate</th>
            <th>Avg dur.</th>
            <th>Booking</th>
            <th>Escalation</th>
            <th>Follow-up</th>
            <th>Cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const hasOutcomes = r.outcomes.analyzed_count > 0;
            const ncRate = r.call_volume.total > 0
              ? r.call_volume.not_connected / r.call_volume.total
              : 0;
            return (
              <tr key={r.agent_id}>
                <td style={{ fontFamily: "ui-monospace, monospace", fontSize: 11, maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.agent_id}</td>
                <td>{r.call_volume.total}</td>
                <td style={{ color: "var(--green)" }}>{r.call_volume.connected}</td>
                <td>{pct(r.call_volume.connection_rate)}</td>
                <td style={{ color: "var(--red)" }}>{r.call_volume.not_connected}</td>
                <td className="muted">{pct(ncRate)}</td>
                <td className="muted">{dur(r.duration.avg_seconds)}</td>
                <td>{hasOutcomes ? pct(r.outcomes.booking.pct_of_analyzed) : "—"}</td>
                <td>{hasOutcomes ? pct(r.outcomes.escalation.pct_of_analyzed) : "—"}</td>
                <td>{hasOutcomes ? pct(r.outcomes.follow_up.pct_of_analyzed) : "—"}</td>
                <td className="muted">{cost(r.cost.total)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── By-batch table ────────────────────────────────────────────────────────────

function BatchTable({ rows }: { rows: BatchStats[] }) {
  if (rows.length === 0) return <p className="muted" style={{ fontSize: 13 }}>No data.</p>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table>
        <thead>
          <tr>
            <th>Batch ID</th>
            <th>Status</th>
            <th>Total</th>
            <th>Connected</th>
            <th>Conn. rate</th>
            <th>Not conn.</th>
            <th>NC rate</th>
            <th>Avg dur.</th>
            <th>Booking</th>
            <th>Escalation</th>
            <th>Follow-up</th>
            <th>Cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const hasOutcomes = r.outcomes.analyzed_count > 0;
            const ncRate = r.call_volume.total > 0
              ? r.call_volume.not_connected / r.call_volume.total
              : 0;
            return (
              <tr key={r.batch_id}>
                <td style={{ fontFamily: "ui-monospace, monospace", fontSize: 11, maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.batch_id}</td>
                <td><span className={`badge ${r.batch_status === "completed" ? "ok" : r.batch_status === "failed" ? "err" : "warn"}`}>{r.batch_status ?? "—"}</span></td>
                <td>{r.call_volume.total}</td>
                <td style={{ color: "var(--green)" }}>{r.call_volume.connected}</td>
                <td>{pct(r.call_volume.connection_rate)}</td>
                <td style={{ color: "var(--red)" }}>{r.call_volume.not_connected}</td>
                <td className="muted">{pct(ncRate)}</td>
                <td className="muted">{dur(r.duration.avg_seconds)}</td>
                <td>{hasOutcomes ? pct(r.outcomes.booking.pct_of_analyzed) : "—"}</td>
                <td>{hasOutcomes ? pct(r.outcomes.escalation.pct_of_analyzed) : "—"}</td>
                <td>{hasOutcomes ? pct(r.outcomes.follow_up.pct_of_analyzed) : "—"}</td>
                <td className="muted">{cost(r.cost.total)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type View = "overview" | "by-agent" | "by-batch" | "timeseries";

export default function AnalyticsPage() {
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [clientId, setClientId] = useState("");
  const [agents, setAgents] = useState<ClientAgent[]>([]);
  const [batches, setBatches] = useState<ClientBatchSummary[]>([]);
  const [agentId, setAgentId] = useState("");
  const [batchId, setBatchId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [granularity, setGranularity] = useState<"day" | "week">("day");
  const [view, setView] = useState<View>("overview");

  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [byAgent, setByAgent] = useState<AgentStats[] | null>(null);
  const [byBatch, setByBatch] = useState<BatchStats[] | null>(null);
  const [timeseries, setTimeseries] = useState<TimeseriesPoint[] | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminApi.listClients("active").then(setClients).catch(() => {});
  }, []);

  // Load agents and batches when client changes
  useEffect(() => {
    setAgents([]);
    setBatches([]);
    setAgentId("");
    setBatchId("");
    if (!clientId) return;
    adminApi.getClientAgents(clientId).then(setAgents).catch(() => {});
    adminApi.listClientBatches(clientId).then(setBatches).catch(() => {});
  }, [clientId]);

  const load = useCallback(async () => {
    if (!clientId) return;
    setLoading(true);
    setError(null);
    const base = {
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    };
    try {
      if (view === "overview") {
        setOverview(await adminApi.getClientAnalyticsOverview(clientId, {
          ...base,
          agent_id: agentId || undefined,
          batch_id: batchId || undefined,
        }));
      } else if (view === "by-agent") {
        // by-agent groups BY agent, so filter by batch only
        setByAgent(await adminApi.getClientAnalyticsByAgent(clientId, {
          ...base,
          batch_id: batchId || undefined,
        }));
      } else if (view === "by-batch") {
        // by-batch groups BY batch, so filter by agent only
        setByBatch(await adminApi.getClientAnalyticsByBatch(clientId, {
          ...base,
          agent_id: agentId || undefined,
        }));
      } else {
        setTimeseries(await adminApi.getClientAnalyticsTimeseries(clientId, {
          ...base,
          agent_id: agentId || undefined,
          batch_id: batchId || undefined,
          granularity,
        }));
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, view, agentId, batchId, dateFrom, dateTo, granularity]);

  useEffect(() => { load(); }, [load]);

  const VIEWS: { key: View; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "by-agent", label: "By Agent" },
    { key: "by-batch", label: "By Batch" },
    { key: "timeseries", label: "Timeseries" },
  ];

  return (
    <div className="page-enter">
      <h1>Analytics</h1>
      <p className="subtitle">Per-client call analytics with outcome breakdown.</p>

      {/* Filters */}
      <div className="card">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "flex-end" }}>
          <div style={{ flex: "2 1 180px" }}>
            <label>Client</label>
            <select value={clientId} onChange={(e) => setClientId(e.target.value)}>
              <option value="">— Select a client —</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>

          {/* Agent filter — only relevant when not on by-agent tab */}
          {view !== "by-agent" && (
            <div style={{ flex: "2 1 160px" }}>
              <label>Agent</label>
              <select value={agentId} onChange={(e) => setAgentId(e.target.value)} disabled={!clientId}>
                <option value="">All agents</option>
                {agents.filter((a) => a.enabled).map((a) => (
                  <option key={a.voice_agent_id} value={a.voice_agent_id}>
                    {a.display_name || a.agent_name || a.voice_agent_id}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Batch filter — only relevant when not on by-batch tab */}
          {view !== "by-batch" && (
            <div style={{ flex: "2 1 160px" }}>
              <label>Batch</label>
              <select value={batchId} onChange={(e) => setBatchId(e.target.value)} disabled={!clientId}>
                <option value="">All batches</option>
                {batches.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.id.slice(0, 8)}… · {b.status} · {b.agent_id.slice(0, 10)}…
                  </option>
                ))}
              </select>
            </div>
          )}

          <div style={{ flex: "1 1 120px" }}>
            <label>From</label>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div style={{ flex: "1 1 120px" }}>
            <label>To</label>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          {view === "timeseries" && (
            <div style={{ flex: "1 1 110px" }}>
              <label>Granularity</label>
              <select value={granularity} onChange={(e) => setGranularity(e.target.value as "day" | "week")}>
                <option value="day">Day</option>
                <option value="week">Week</option>
              </select>
            </div>
          )}
          <div style={{ flexShrink: 0, marginBottom: 14 }}>
            <button onClick={load} disabled={!clientId || loading}>
              {loading ? <><span className="spinner" />Loading…</> : "Apply"}
            </button>
          </div>
        </div>
      </div>

      {!clientId && (
        <div className="empty-state">Select a client to view analytics.</div>
      )}

      {clientId && (
        <>
          <div className="tabs" style={{ marginBottom: 20 }}>
            {VIEWS.map((v) => (
              <button key={v.key} className={view === v.key ? "active" : ""} onClick={() => setView(v.key)}>
                {v.label}
              </button>
            ))}
          </div>

          {error && <div className="error-box">{error}</div>}

          {loading && (
            <div className="card">
              <div className="stat-grid">
                {[0,1,2,3].map((i) => (
                  <div key={i} className="stat-card">
                    <div className="skeleton skeleton-row w-60" style={{ height: 11, marginBottom: 10 }} />
                    <div className="skeleton skeleton-row w-40" style={{ height: 26 }} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {!loading && view === "overview" && overview && (
            <>
              {/* Volume */}
              <div className="card">
                <h2>Call volume</h2>
                <div className="stat-grid">
                  <StatCard label="Total calls" value={String(overview.call_volume.total)} />
                  <StatCard label="Connected" value={String(overview.call_volume.connected)} color="var(--green)" sub="status: completed" />
                  <StatCard label="Connection rate" value={pct(overview.call_volume.connection_rate)} color="var(--green)" />
                  <StatCard label="Not connected" value={String(overview.call_volume.not_connected)} color="var(--red)" sub="no-answer, busy, failed…" />
                  <StatCard label="Pending / running" value={String(overview.call_volume.pending)} color={overview.call_volume.pending > 0 ? "var(--amber)" : undefined} sub="scheduled · in-progress" />
                </div>
                {Object.keys(overview.not_connected_breakdown).length > 0 && (
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 4 }}>
                    {Object.entries(overview.not_connected_breakdown).map(([k, v]) => (
                      <span key={k} className="muted" style={{ fontSize: 12 }}>
                        <strong style={{ color: "var(--text)" }}>{v}</strong> {k}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Duration + Cost */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 0 }}>
                <div className="card">
                  <h2>Duration</h2>
                  <div className="stat-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                    <StatCard label="Avg" value={dur(overview.duration.avg_seconds)} />
                    <StatCard label="P50" value={dur(overview.duration.p50_seconds)} />
                    <StatCard label="P90" value={dur(overview.duration.p90_seconds)} />
                    <StatCard label="Total" value={dur(overview.duration.total_seconds)} />
                  </div>
                </div>
                <div className="card">
                  <h2>Cost</h2>
                  <div className="stat-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                    <StatCard label="Total" value={`$${overview.cost.total.toFixed(2)}`} />
                    <StatCard label="Avg / call" value={cost(overview.cost.avg_per_call)} />
                    <StatCard label="Avg / connected" value={cost(overview.cost.avg_per_connected)} />
                    <StatCard label="Retries" value={String(overview.retry_stats.calls_with_retry)} sub={overview.retry_stats.avg_retries != null ? `avg ${overview.retry_stats.avg_retries.toFixed(1)}` : undefined} />
                  </div>
                </div>
              </div>

              {/* Outcomes */}
              <div className="card" style={{ marginTop: 16 }}>
                <h2>Outcome breakdown</h2>
                <OutcomeBars overview={overview} />
              </div>
            </>
          )}

          {!loading && view === "by-agent" && byAgent && (
            <div className="card">
              <h2>By Agent</h2>
              <AgentTable rows={byAgent} />
            </div>
          )}

          {!loading && view === "by-batch" && byBatch && (
            <div className="card">
              <h2>By Batch</h2>
              <BatchTable rows={byBatch} />
            </div>
          )}

          {!loading && view === "timeseries" && timeseries && (
            <div className="card">
              <h2>Call volume over time</h2>
              <TimeseriesChart points={timeseries} />

              {/* Timeseries outcome summary */}
              {timeseries.length > 0 && Object.keys(timeseries[0].outcomes).length > 0 && (
                <div style={{ marginTop: 20, overflowX: "auto" }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Total</th>
                        <th>Connected</th>
                        {OUTCOME_KEYS.map((k) => <th key={k}>{OUTCOME_LABELS[k]}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {timeseries.map((p) => (
                        <tr key={p.date}>
                          <td style={{ fontFamily: "ui-monospace, monospace", fontSize: 12 }}>{p.date.slice(0, 10)}</td>
                          <td>{p.total}</td>
                          <td>{p.connected}</td>
                          {OUTCOME_KEYS.map((k) => <td key={k} className="muted">{p.outcomes[k] ?? 0}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
