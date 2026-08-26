"use client";

import { useState } from "react";
import Link from "next/link";
import { publicApi } from "../../../lib/publicApi";

export default function RegisterPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await publicApi.register(name, email || undefined);
      setDone(true);
    } catch (err: unknown) {
      if (err instanceof Error && (err as { status?: number }).status === 429) {
        setError("Too many requests. Please wait a few minutes before trying again.");
      } else {
        setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <main className="main public">
        <div className="card page-enter" style={{ textAlign: "center", padding: "40px 24px" }}>
          <div style={{ fontSize: 40, marginBottom: 16, opacity: 0.9 }}>✓</div>
          <h1 style={{ fontSize: 20, marginBottom: 8 }}>Request received</h1>
          <p style={{ color: "var(--muted)", margin: 0 }}>
            We&apos;ll review your request and send you an API key once approved.
          </p>
          <p style={{ marginTop: 20, marginBottom: 0 }}>
            <Link href="/portal" style={{ fontSize: 13, color: "var(--muted)" }}>
              Already have an API key? Sign in →
            </Link>
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="main public">
      <div className="card page-enter">
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: 20, marginBottom: 4 }}>Request API access</h1>
          <p className="subtitle" style={{ marginBottom: 0 }}>
            Tell us who you are and we&apos;ll get back to you once approved.
          </p>
        </div>

        {error && <div className="error-box">{error}</div>}

        <form onSubmit={submit}>
          <div>
            <label>Organization name *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Acme Health"
              required
              disabled={busy}
            />
          </div>
          <div>
            <label>Contact email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="ops@example.com"
              disabled={busy}
            />
          </div>
          <button type="submit" disabled={busy || !name.trim()} style={{ width: "100%" }}>
            {busy ? <><span className="spinner" />Submitting…</> : "Request access"}
          </button>
        </form>

        <div style={{ marginTop: 20, display: "flex", justifyContent: "space-between", fontSize: 13, color: "var(--muted)" }}>
          <Link href="/portal">Already have an API key? Sign in →</Link>
          <Link href="/login">Operator login →</Link>
        </div>
      </div>
    </main>
  );
}
