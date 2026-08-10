"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { publicApi } from "../../../../lib/publicApi";
import type { ClaimPeek, ClaimResult } from "../../../../lib/types";

export default function ClaimPage() {
  const params = useParams();
  const token = params.token as string;

  const [peek, setPeek] = useState<ClaimPeek | null>(null);
  const [result, setResult] = useState<ClaimResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    publicApi
      .claimPeek(token)
      .then(setPeek)
      .catch((err: unknown) => {
        if (err instanceof Error && (err as { status?: number }).status === 404) {
          setError("This link is invalid, expired, or has already been used.");
        } else if (err instanceof Error && (err as { status?: number }).status === 503) {
          setError("The key store is temporarily unavailable. Please try again in a moment.");
        } else {
          setError("Could not load this link. Please try again.");
        }
      });
  }, [token]);

  async function reveal() {
    setBusy(true);
    try {
      const res = await publicApi.claimBurn(token);
      setResult(res);
    } catch (err: unknown) {
      if (err instanceof Error && (err as { status?: number }).status === 404) {
        setError("This link has already been used or expired.");
      } else {
        setError("Failed to reveal key. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  function copy() {
    if (!result) return;
    navigator.clipboard.writeText(result.api_key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (error) {
    return (
      <main className="main public">
        <div className="card page-enter" style={{ borderColor: "rgba(255,95,109,0.35)" }}>
          <h1 style={{ fontSize: 20, marginBottom: 12 }}>Invalid link</h1>
          <div className="error-box" style={{ marginBottom: 0 }}>{error}</div>
        </div>
      </main>
    );
  }

  if (result) {
    return (
      <main className="main public">
        <div className="card page-enter" style={{ borderColor: "rgba(55,201,120,0.30)" }}>
          <div style={{ marginBottom: 16 }}>
            <h1 style={{ fontSize: 20, marginBottom: 4 }}>Your API key</h1>
            <p style={{ color: "var(--muted)", fontSize: 13, margin: 0 }}>
              For <strong>{result.client_name}</strong>. Store this securely — it won&apos;t be shown again.
            </p>
          </div>
          <pre className="key-reveal">{result.api_key}</pre>
          <div className="btn-row" style={{ marginTop: 14 }}>
            <button onClick={copy} style={{ width: "100%" }}>
              {copied ? "✓ Copied to clipboard!" : "Copy to clipboard"}
            </button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="main public">
      <div className="card page-enter">
        {peek ? (
          <>
            <div style={{ marginBottom: 20 }}>
              <h1 style={{ fontSize: 20, marginBottom: 4 }}>API key for {peek.client_name}</h1>
              <p style={{ color: "var(--muted)", fontSize: 13, margin: 0 }}>
                This link expires in{" "}
                <strong>
                  {Math.max(0, Math.floor(peek.expires_in_seconds / 3600))}h{" "}
                  {Math.floor((peek.expires_in_seconds % 3600) / 60)}m
                </strong>.
                {" "}The key will be shown once — store it securely.
              </p>
            </div>
            <button onClick={reveal} disabled={busy} style={{ width: "100%" }}>
              {busy ? <><span className="spinner" />Revealing…</> : "Reveal API key"}
            </button>
          </>
        ) : (
          <div style={{ textAlign: "center", padding: "24px 0" }}>
            <span className="spinner" style={{ width: 20, height: 20, borderWidth: 3 }} />
            <p className="muted" style={{ marginTop: 12 }}>Loading link…</p>
          </div>
        )}
      </div>
    </main>
  );
}
