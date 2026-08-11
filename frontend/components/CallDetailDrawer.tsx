"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "@/lib/api";
import { adminApi } from "@/lib/adminApi";
import AudioPlayer from "@/components/AudioPlayer";
import type { CallAnalysisResult, CallDetail } from "@/lib/types";

const successStyle = {
  background: "rgba(55,201,120,0.10)",
  border: "1px solid rgba(55,201,120,0.35)",
  color: "var(--green)",
  borderRadius: 8,
  padding: "8px 14px",
  marginBottom: 12,
  fontSize: 13,
  animation: "page-in 0.25s var(--ease-glass)",
} as const;

const OUTCOME_COLORS: Record<string, string> = {
  booking: "var(--green)",
  escalation: "var(--amber)",
  not_interested: "var(--red)",
  no_output: "var(--muted)",
  follow_up: "var(--accent)",
  other: "var(--muted)",
  not_reached: "var(--muted)",
};

const URGENCY_COLORS: Record<string, string> = {
  low: "var(--muted)",
  medium: "var(--amber)",
  high: "var(--red)",
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

function UrgencyBadge({ urgency }: { urgency: string }) {
  const color = URGENCY_COLORS[urgency] ?? "var(--muted)";
  return (
    <span style={{
      fontSize: 11, padding: "2px 8px", borderRadius: 20, fontWeight: 600,
      background: `color-mix(in srgb, ${color} 14%, transparent)`,
      border: `1px solid color-mix(in srgb, ${color} 35%, transparent)`,
      color,
      whiteSpace: "nowrap",
    }}>
      {urgency}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cls = status === "completed" ? "ok" : status === "failed" || status === "error" ? "err" : "warn";
  return <span className={`badge ${cls}`}>{status}</span>;
}

export default function CallDetailDrawer({
  mode,
  clientId,
  callId,
  onClose,
}: {
  mode: "admin" | "tenant";
  clientId?: string;
  callId: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<CallDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeResult, setAnalyzeResult] = useState<CallAnalysisResult | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  const fetchDetail = () =>
    mode === "admin" && clientId
      ? adminApi.getClientCallDetail(clientId, callId)
      : api.getCallDetail(callId);

  const runAnalyzeCall = () =>
    mode === "admin" && clientId
      ? adminApi.analyzeClientCall(clientId, callId)
      : api.analyzeCall(callId);

  useEffect(() => {
    setLoading(true);
    fetchDetail()
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, clientId, callId]);

  async function runAnalyze() {
    setAnalyzing(true);
    try {
      const result = await runAnalyzeCall();
      setAnalyzeResult(result);
      const updated = await fetchDetail();
      setDetail(updated);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  }

  if (!mounted) return null;

  return createPortal(
    <div style={{
      position: "fixed", inset: 0, zIndex: 200,
      background: "rgba(0,0,0,0.6)",
      backdropFilter: "blur(4px)",
      display: "flex", alignItems: "flex-start", justifyContent: "flex-end",
    }} onClick={onClose}>
      <div style={{
        width: "min(640px, 100vw)", height: "100vh",
        background: "var(--bg)", borderLeft: "1px solid var(--glass-border)",
        boxShadow: "-8px 0 40px rgba(0,0,0,0.25)",
        overflowY: "auto", padding: 28,
        animation: "slide-right 0.25s var(--ease-glass)",
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 16 }}>Call Detail</h2>
          <button className="secondary" style={{ fontSize: 12, padding: "4px 12px" }} onClick={onClose}>✕ Close</button>
        </div>

        {error && <div className="error-box">{error}</div>}
        {loading ? (
          <div>
            {[80, 60, 100, 50].map((w, i) => (
              <div key={i} className={`skeleton skeleton-row w-${w}`} style={{ height: 14, marginBottom: 10 }} />
            ))}
          </div>
        ) : detail ? (
          <>
            <table style={{ marginBottom: 16 }}>
              <tbody>
                <tr><td className="muted" style={{ width: 130, paddingRight: 12 }}>Platform status</td><td><StatusBadge status={detail.status} /></td></tr>
                <tr><td className="muted">Contact</td><td>{detail.contact_number ?? "—"}</td></tr>
                <tr><td className="muted">From</td><td>{detail.from_number ?? "—"}</td></tr>
                <tr><td className="muted">Duration</td><td>{detail.duration != null ? `${detail.duration.toFixed(1)}s` : "—"}</td></tr>
                <tr><td className="muted">Cost</td><td>{detail.cost != null ? `$${detail.cost.toFixed(4)}` : "—"}</td></tr>
                <tr><td className="muted">Hangup reason</td><td>{detail.hangup_reason ?? "—"}</td></tr>
                <tr><td className="muted">Created</td><td>{new Date(detail.created_at).toLocaleString()}</td></tr>
                {detail.recording_url && (
                  <tr>
                    <td className="muted">Recording</td>
                    <td><AudioPlayer url={detail.recording_url} /></td>
                  </tr>
                )}
              </tbody>
            </table>

            {/* Analysis */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                <strong>Analysis</strong>
                {detail.status === "completed" && detail.transcript && (
                  <button className="secondary" style={{ fontSize: 12, padding: "3px 10px" }}
                    onClick={runAnalyze} disabled={analyzing}>
                    {analyzing ? <><span className="spinner" />Analyzing…</> : detail.analysis ? "Re-analyze" : "Analyze now"}
                  </button>
                )}
              </div>
              {analyzeResult && (
                <div style={{ ...successStyle, marginBottom: 10 }}>✓ Analysis complete.</div>
              )}
              {detail.analysis ? (
                <div style={{
                  background: "var(--glass-bg)", border: "1px solid var(--glass-border)",
                  borderRadius: "var(--radius)", padding: "14px 16px",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
                    <OutcomeBadge outcome={detail.analysis.outcome} />
                    {detail.analysis.urgency && <UrgencyBadge urgency={detail.analysis.urgency} />}
                    {detail.analysis.model_used && (
                      <span className="muted" style={{ fontSize: 11 }}>
                        {detail.analysis.model_used}
                        {detail.analysis.confidence != null && ` · ${Math.round(detail.analysis.confidence * 100)}% confidence`}
                      </span>
                    )}
                  </div>
                  {detail.analysis.summary && (
                    <p style={{ margin: "0 0 8px", fontSize: 13 }}>{detail.analysis.summary}</p>
                  )}
                  {detail.analysis.reason && (
                    <p className="muted" style={{ margin: "0 0 8px", fontSize: 12 }}>{detail.analysis.reason}</p>
                  )}
                  {detail.analysis.symptoms_reported && detail.analysis.symptoms_reported.length > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      <strong style={{ fontSize: 12 }}>Symptoms reported:</strong>
                      <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 12 }}>
                        {detail.analysis.symptoms_reported.map((s, i) => <li key={i}>{s}</li>)}
                      </ul>
                    </div>
                  )}
                  {detail.analysis.requests && detail.analysis.requests.length > 0 && (
                    <div>
                      <strong style={{ fontSize: 12 }}>Patient requests:</strong>
                      <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 12 }}>
                        {detail.analysis.requests.map((r, i) => <li key={i}>{r}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <p className="muted" style={{ fontSize: 13 }}>
                  {detail.status !== "completed" ? "Analysis only available for completed calls." : "Not yet analyzed."}
                </p>
              )}
            </div>

            {detail.transcript && (
              <div style={{ marginBottom: 16 }}>
                <strong style={{ display: "block", marginBottom: 8 }}>Transcript</strong>
                <pre style={{ maxHeight: 280, overflowY: "auto", fontSize: 12, lineHeight: 1.6 }}>{detail.transcript}</pre>
              </div>
            )}

            {detail.extracted_data && Object.keys(detail.extracted_data).length > 0 && (
              <div>
                <strong style={{ display: "block", marginBottom: 8 }}>Extracted data</strong>
                <pre style={{ fontSize: 12 }}>{JSON.stringify(detail.extracted_data, null, 2)}</pre>
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>,
    document.body
  );
}
