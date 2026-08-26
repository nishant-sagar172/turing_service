"use client";

import { useEffect, useState } from "react";
import { adminApi } from "../../../lib/adminApi";
import type { CatalogAgent, SyncResult } from "../../../lib/types";

export default function AgentsPage() {
  const [agents, setAgents] = useState<CatalogAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    setLoading(true);
    adminApi
      .listCatalogAgents()
      .then(setAgents)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => { reload(); }, []);

  async function syncNow() {
    setSyncing(true);
    setSyncResult(null);
    try {
      const result = await adminApi.syncAgents();
      setSyncResult(result);
      reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="page-enter">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <h1>Agent Catalog</h1>
        <button onClick={syncNow} disabled={syncing}>
          {syncing ? <><span className="spinner" />Syncing…</> : "↻ Sync now"}
        </button>
      </div>
      <p className="subtitle">All agents from the voice engine. Sync to detect additions, removals, and drift.</p>

      {error && <div className="error-box">{error}</div>}

      {syncResult && (
        <div style={{
          background: "rgba(55,201,120,0.10)",
          border: "1px solid rgba(55,201,120,0.35)",
          color: "var(--green)",
          borderRadius: 8,
          padding: "10px 14px",
          marginBottom: 16,
          fontSize: 13,
          animation: "page-in 0.25s var(--ease-glass)",
        }}>
          ✓ Sync complete — {syncResult.synced} synced, {syncResult.removed} removed, {syncResult.drift_events} drift event(s) raised.
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table>
          <thead>
            <tr>
              <th>Agent ID</th>
              <th>Name</th>
              <th>Status</th>
              <th>Present</th>
              <th>Last synced</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <>
                {[0, 1, 2].map((i) => (
                  <tr key={i}>
                    {[60, 80, 40, 40, 60].map((w, j) => (
                      <td key={j}>
                        <div className={`skeleton skeleton-row w-${w}`} style={{ height: 12, margin: 0 }} />
                      </td>
                    ))}
                  </tr>
                ))}
              </>
            )}
            {!loading && agents.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: 0 }}>
                  <div className="empty-state">No agents in catalog. Run sync first.</div>
                </td>
              </tr>
            )}
            {agents.map((a) => (
              <tr key={a.voice_agent_id}>
                <td><code style={{ fontSize: 12 }}>{a.voice_agent_id}</code></td>
                <td>{a.agent_name ?? "—"}</td>
                <td>
                  {a.agent_status === "active"
                    ? <span className="badge ok">active</span>
                    : <span className="badge warn">{a.agent_status ?? "unknown"}</span>}
                </td>
                <td>
                  {a.is_present
                    ? <span className="badge ok">yes</span>
                    : <span className="badge err">missing</span>}
                </td>
                <td className="muted">
                  {a.last_synced_at ? new Date(a.last_synced_at).toLocaleString() : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
