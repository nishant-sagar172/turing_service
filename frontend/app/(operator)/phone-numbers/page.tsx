"use client";

import { useEffect, useState } from "react";
import { adminApi } from "@/lib/adminApi";
import type { PhoneNumberCatalogEntry, PhoneNumberSyncResult } from "@/lib/types";

export default function PhoneNumbersPage() {
  const [catalog, setCatalog] = useState<PhoneNumberCatalogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<PhoneNumberSyncResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    setLoading(true);
    adminApi
      .listPhoneNumberCatalog()
      .then(setCatalog)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(() => { reload(); }, []);

  async function syncNow() {
    setSyncing(true);
    setSyncResult(null);
    try {
      const result = await adminApi.syncPhoneNumbers();
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
        <h1>Phone Numbers</h1>
        <button onClick={syncNow} disabled={syncing}>
          {syncing ? <><span className="spinner" />Syncing…</> : "↻ Sync now"}
        </button>
      </div>
      <p className="subtitle">
        All numbers on the voice engine account. Sync to refresh, then assign numbers to clients from their detail page.
      </p>

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
          ✓ Sync complete — {syncResult.synced} synced, {syncResult.removed} removed.
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table>
          <thead>
            <tr>
              <th>Phone number</th>
              <th>Provider</th>
              <th>Rented</th>
              <th>Present</th>
              <th>Last synced</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <>
                {[0, 1, 2].map((i) => (
                  <tr key={i}>
                    {[60, 40, 40, 40, 60].map((w, j) => (
                      <td key={j}>
                        <div className={`skeleton skeleton-row w-${w}`} style={{ height: 12, margin: 0 }} />
                      </td>
                    ))}
                  </tr>
                ))}
              </>
            )}
            {!loading && catalog.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: 0 }}>
                  <div className="empty-state">No numbers in catalog. Run sync first.</div>
                </td>
              </tr>
            )}
            {catalog.map((n) => (
              <tr key={n.id}>
                <td>
                  <span className="badge warn" style={{ fontFamily: "ui-monospace, monospace", letterSpacing: 0 }}>
                    {n.phone_number}
                  </span>
                </td>
                <td className="muted">{n.telephony_provider ?? "—"}</td>
                <td>
                  {n.rented != null ? (
                    <span className={`badge ${n.rented ? "ok" : "warn"}`}>{n.rented ? "yes" : "no"}</span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  {n.is_present
                    ? <span className="badge ok">yes</span>
                    : <span className="badge err">missing</span>}
                </td>
                <td className="muted">
                  {n.last_synced_at ? new Date(n.last_synced_at).toLocaleString() : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
