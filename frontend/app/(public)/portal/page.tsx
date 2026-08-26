"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "../../../lib/api";
import { getApiKey, setApiKey, clearApiKey } from "../../../lib/session";
import Modal from "../../../components/Modal";
import type { KeySummary, MeResponse } from "../../../lib/types";

export default function PortalPage() {
  const router = useRouter();
  const [signedIn, setSignedIn] = useState(false);
  const [tab, setTab] = useState<"key" | "email">("key");
  const [inputKey, setInputKey] = useState("");
  const [inputName, setInputName] = useState("");
  const [inputEmail, setInputEmail] = useState("");
  const [me, setMe] = useState<MeResponse | null>(null);
  const [keys, setKeys] = useState<KeySummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<KeySummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const currentPrefix = getApiKey()?.slice(0, 11) ?? null;

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [meRes, keysRes] = await Promise.all([api.me(), api.myKeys()]);
      setMe(meRes);
      setKeys(keysRes);
    } catch (e: unknown) {
      if (e instanceof Error && (e as { status?: number }).status === 401) {
        clearApiKey();
        setSignedIn(false);
      } else {
        setError(e instanceof Error ? e.message : "Failed to load");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (getApiKey()) setSignedIn(true);
  }, []);

  useEffect(() => {
    if (signedIn) loadData();
  }, [signedIn, loadData]);

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    if (!inputKey.trim()) return;
    setApiKey(inputKey.trim());
    setSignedIn(true);
    setInputKey("");
  }

  async function signInByEmail(e: React.FormEvent) {
    e.preventDefault();
    if (!inputName.trim() || !inputEmail.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.portalLookup(inputName.trim(), inputEmail.trim());
      setApiKey(res.api_key);
      setSignedIn(true);
      setInputName("");
      setInputEmail("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  function signOut() {
    clearApiKey();
    setMe(null);
    setKeys([]);
    setSignedIn(false);
  }

  async function issueKey() {
    setBusy(true);
    try {
      const res = await api.issueMyKey("portal");
      setNewKey(res.api_key);
      loadData();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function confirmRevoke() {
    if (!revokeTarget) return;
    setBusy(true);
    try {
      await api.revokeMyKey(revokeTarget.id);
      setRevokeTarget(null);
      loadData();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  const activeKeys = keys.filter((k) => k.status === "active");

  if (!signedIn) {
    return (
      <main className="main public">
        <div className="card page-enter" style={{ position: "relative" }}>
          <button
            onClick={() => router.back()}
            aria-label="Go back"
            style={{
              position: "absolute", top: 12, right: 12,
              background: "none", border: "1px solid var(--border)",
              borderRadius: "var(--radius)", cursor: "pointer",
              color: "var(--text-muted)", fontSize: 16, lineHeight: 1,
              width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >
            ✕
          </button>

          <div style={{ marginBottom: 20 }}>
            <h1 style={{ fontSize: 20, marginBottom: 4 }}>Client Portal</h1>
            <p className="subtitle" style={{ marginBottom: 0 }}>Sign in to manage your account.</p>
          </div>

          {/* Tab switcher */}
          <div style={{ display: "flex", gap: 4, marginBottom: 20, borderBottom: "1px solid var(--border)", paddingBottom: 0 }}>
            {(["key", "email"] as const).map((t) => (
              <button
                key={t}
                onClick={() => { setTab(t); setError(null); }}
                style={{
                  background: "none", border: "none", cursor: "pointer",
                  padding: "6px 12px", fontSize: 13, fontWeight: tab === t ? 600 : 400,
                  color: tab === t ? "var(--text)" : "var(--text-muted)",
                  borderBottom: tab === t ? "2px solid var(--accent)" : "2px solid transparent",
                  marginBottom: -1,
                }}
              >
                {t === "key" ? "API Key" : "Name & Email"}
              </button>
            ))}
          </div>

          {error && <div className="error-box">{error}</div>}

          {tab === "key" ? (
            <form onSubmit={signIn}>
              <label>API Key</label>
              <input
                type="password"
                value={inputKey}
                onChange={(e) => setInputKey(e.target.value)}
                placeholder="tk_…"
                autoComplete="off"
              />
              <button type="submit" disabled={!inputKey.trim()} style={{ width: "100%" }}>
                Sign in
              </button>
            </form>
          ) : (
            <form onSubmit={signInByEmail}>
              <label>Client Name</label>
              <input
                type="text"
                value={inputName}
                onChange={(e) => setInputName(e.target.value)}
                placeholder="Acme Hospital"
                autoComplete="organization"
              />
              <label style={{ marginTop: 12 }}>Email</label>
              <input
                type="email"
                value={inputEmail}
                onChange={(e) => setInputEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
              />
              <button
                type="submit"
                disabled={!inputName.trim() || !inputEmail.trim() || loading}
                style={{ width: "100%", marginTop: 4 }}
              >
                {loading ? <><span className="spinner" />Signing in…</> : "Sign in"}
              </button>
            </form>
          )}

          <p style={{ textAlign: "center", margin: "14px 0 0", fontSize: 13 }}>
            <button className="secondary" onClick={() => router.back()} style={{ fontSize: 13, padding: "4px 12px" }}>
              ← Go back
            </button>
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="main public page-enter" style={{ maxWidth: 680 }}>
      {error && <div className="error-box">{error}</div>}

      {me && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 10 }}>
            <div>
              <h1 style={{ fontSize: 18, margin: "0 0 4px" }}>{me.name}</h1>
              <p className="muted" style={{ margin: 0, fontSize: 12 }}>{me.slug} · {me.contact_email ?? "no email"}</p>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span className={`badge ${me.status === "active" ? "ok" : "warn"}`}>{me.status}</span>
              <button className="secondary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => router.back()}>← Back</button>
              <button className="secondary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={signOut}>Sign out</button>
            </div>
          </div>
        </div>
      )}

      {newKey && (
        <div style={{
          background: "rgba(55,201,120,0.08)",
          border: "1px solid rgba(55,201,120,0.30)",
          borderRadius: "var(--radius)",
          padding: 16,
          marginBottom: 20,
          animation: "page-in 0.3s var(--ease-glass)",
        }}>
          <p style={{ margin: "0 0 8px", fontWeight: 600, color: "var(--green)" }}>New API key (shown once):</p>
          <pre className="key-reveal">{newKey}</pre>
          <div className="btn-row" style={{ marginTop: 10 }}>
            <button onClick={() => { navigator.clipboard.writeText(newKey); setCopied(true); setTimeout(() => setCopied(false), 2000); }}>
              {copied ? "✓ Copied!" : "Copy"}
            </button>
            <button className="secondary" onClick={() => setNewKey(null)}>Dismiss</button>
          </div>
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>API Keys</h2>
        <button onClick={issueKey} disabled={busy || loading} style={{ fontSize: 13 }}>
          {busy ? <><span className="spinner" />Issuing…</> : "+ New key"}
        </button>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table>
          <thead>
            <tr><th>Prefix</th><th>Label</th><th>Status</th><th>Last used</th><th>Created</th><th></th></tr>
          </thead>
          <tbody>
            {loading && (
              <>
                {[0, 1].map((i) => (
                  <tr key={i}>
                    {[60, 40, 40, 60, 60, 40].map((w, j) => (
                      <td key={j}><div className={`skeleton skeleton-row w-${w}`} style={{ height: 12, margin: 0 }} /></td>
                    ))}
                  </tr>
                ))}
              </>
            )}
            {keys.map((k) => (
              <tr key={k.id} style={k.key_prefix === currentPrefix ? { background: "var(--glass-bg-active)" } : {}}>
                <td>
                  <code style={{ fontSize: 12 }}>{k.key_prefix}…</code>
                  {k.key_prefix === currentPrefix && (
                    <span className="badge ok" style={{ marginLeft: 6, fontSize: 10 }}>current</span>
                  )}
                </td>
                <td className="muted">{k.label ?? "—"}</td>
                <td><span className={`badge ${k.status === "active" ? "ok" : "err"}`}>{k.status}</span></td>
                <td className="muted">{k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : "never"}</td>
                <td className="muted">{new Date(k.created_at).toLocaleDateString()}</td>
                <td>
                  {k.status === "active" && (
                    <button className="danger" style={{ fontSize: 12, padding: "4px 10px" }}
                      onClick={() => setRevokeTarget(k)}>Revoke</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal
        open={!!revokeTarget}
        title="Revoke API key"
        confirmLabel="Revoke"
        danger
        busy={busy}
        onConfirm={confirmRevoke}
        onClose={() => setRevokeTarget(null)}
      >
        {activeKeys.length === 1 ? (
          <>
            <p style={{ margin: "0 0 8px", color: "var(--amber)", fontWeight: 600 }}>
              Warning: this is your last active key.
            </p>
            <p style={{ margin: 0 }}>
              Revoking it will lock you out immediately. You&apos;ll need to contact support to regain access.
            </p>
          </>
        ) : (
          <p style={{ margin: 0 }}>
            Revoke key <code>{revokeTarget?.key_prefix}…</code>? You&apos;ll lose access with this key immediately.
          </p>
        )}
      </Modal>
    </main>
  );
}
