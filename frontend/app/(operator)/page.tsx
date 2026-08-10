"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { adminApi } from "@/lib/adminApi";
import type { HealthResponse, VoiceEngineStatus } from "@/lib/types";

function SkeletonCard() {
  return (
    <div className="card">
      <div className="skeleton skeleton-row w-40" style={{ height: 18, marginBottom: 16 }} />
      <div className="skeleton skeleton-row w-60" />
      <div className="skeleton skeleton-row w-80" />
      <div className="skeleton skeleton-row w-60" />
    </div>
  );
}

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [engine, setEngine] = useState<VoiceEngineStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [h, e] = await Promise.all([api.health(), adminApi.voiceEngineStatus()]);
      setHealth(h);
      setEngine(e);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const engineOk = engine?.voice_engine === "ok";

  return (
    <div className="page-enter">
      <h1>Dashboard</h1>
      <p className="subtitle">Service &amp; voice engine connectivity at a glance.</p>

      {error && (
        <div className="error-box">
          {error}
          <div className="muted" style={{ marginTop: 6 }}>
            Is the backend running? Check <code>TURING_API_URL</code> and <code>TURING_ADMIN_KEY</code>.
          </div>
        </div>
      )}

      <div className="row">
        {loading && !health ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            <div className="card" style={health ? { boxShadow: "0 0 24px var(--glow-green)" } : undefined}>
              <h2>
                {health && <span className="status-dot ok" />}
                Service
              </h2>
              {health ? (
                <>
                  <p style={{ marginTop: 0 }}>
                    <span className="badge ok">{health.status}</span>
                  </p>
                  <table>
                    <tbody>
                      <tr><td className="muted">Name</td><td>{health.service}</td></tr>
                      <tr><td className="muted">Version</td><td>{health.version}</td></tr>
                      <tr><td className="muted">Environment</td><td>{health.environment}</td></tr>
                    </tbody>
                  </table>
                </>
              ) : (
                <p className="muted">Unavailable</p>
              )}
            </div>

            <div
              className="card"
              style={engine ? { boxShadow: engineOk ? "0 0 24px var(--glow-green)" : "0 0 24px var(--glow-red)" } : undefined}
            >
              <h2>
                {engine && <span className={`status-dot ${engineOk ? "ok" : "err"}`} />}
                Voice Engine
              </h2>
              {engine ? (
                <>
                  <p style={{ marginTop: 0 }}>
                    <span className={`badge ${engineOk ? "ok" : "err"}`}>{engine.voice_engine}</span>{" "}
                    <span className="muted">{engine.base_url}</span>
                  </p>
                  {engine.account ? (
                    <table>
                      <tbody>
                        {Object.entries(engine.account).map(([k, v]) => (
                          <tr key={k}>
                            <td className="muted">{k}</td>
                            <td>{typeof v === "object" ? JSON.stringify(v) : String(v)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="error-box">{engine.detail}</div>
                  )}
                </>
              ) : (
                <p className="muted">Unavailable</p>
              )}
            </div>
          </>
        )}
      </div>

      <button className="secondary" onClick={load} disabled={loading}>
        {loading ? <><span className="spinner" />Refreshing…</> : "↻ Refresh"}
      </button>
    </div>
  );
}
