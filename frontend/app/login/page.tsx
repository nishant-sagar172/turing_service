"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    if (!password.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error((data && data.detail) || `Sign in failed (${res.status})`);
      }
      router.replace("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="main public">
      <div className="card page-enter">
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: 20, marginBottom: 4 }}>Operator Console</h1>
          <p className="subtitle" style={{ marginBottom: 0 }}>Enter the operator password to continue.</p>
        </div>
        {error && <div className="error-box">{error}</div>}
        <form onSubmit={signIn}>
          <label>Password</label>
          {/* Placeholder is deliberately text, not bullet characters: in a
              password field those render identically to real input, so an empty
              field looks filled and the disabled button looks broken. */}
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Operator password"
            autoComplete="current-password"
            autoFocus
            disabled={busy}
          />
          <button type="submit" disabled={!password.trim() || busy} style={{ width: "100%" }}>
            {busy ? <><span className="spinner" />Signing in…</> : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
