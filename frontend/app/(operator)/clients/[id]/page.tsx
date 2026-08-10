"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { adminApi } from "../../../../lib/adminApi";
import Modal from "../../../../components/Modal";
import JsonField from "../../../../components/JsonField";
import AgentVariableForm from "../../../../components/AgentVariableForm";
import type {
  ClientSummary,
  KeySummary,
  ClientConfig,
  ClientAgent,
  CatalogAgent,
  ClientPhoneNumberEntry,
  PhoneNumberCatalogEntry,
  DriftEvent,
  AgentVariables,
  ApproveResult,
} from "../../../../lib/types";

type Tab = "overview" | "keys" | "config" | "agents" | "phone-numbers" | "drift";

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "active" ? "ok" : status === "pending" ? "warn" : status === "suspended" ? "warn" : "err";
  return <span className={`badge ${cls}`}>{status}</span>;
}

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

// ── Keys tab ──────────────────────────────────────────────────────────────────

function KeysTab({ clientId }: { clientId: string }) {
  const [keys, setKeys] = useState<KeySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<KeySummary | null>(null);
  const [issuedKey, setIssuedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    adminApi.listKeys(clientId).then(setKeys).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, [clientId]);

  useEffect(() => { reload(); }, [reload]);

  async function issueKey() {
    setBusy(true);
    try {
      const { api_key } = await adminApi.issueKey(clientId);
      setIssuedKey(api_key);
      reload();
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
      await adminApi.revokeKey(clientId, revokeTarget.id);
      setRevokeTarget(null);
      reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  function copyKey() {
    if (!issuedKey) return;
    navigator.clipboard.writeText(issuedKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const activeCount = keys.filter((k) => k.status === "active").length;

  return (
    <div>
      {error && <div className="error-box">{error}</div>}
      {issuedKey && (
        <div style={{
          background: "rgba(55,201,120,0.08)",
          border: "1px solid rgba(55,201,120,0.30)",
          borderRadius: "var(--radius)",
          padding: 16,
          marginBottom: 16,
          animation: "page-in 0.3s var(--ease-glass)",
        }}>
          <p style={{ margin: "0 0 8px", fontWeight: 600, color: "var(--green)" }}>New API key (shown once):</p>
          <pre className="key-reveal">{issuedKey}</pre>
          <div className="btn-row" style={{ marginTop: 10 }}>
            <button className="secondary" onClick={copyKey}>
              {copied ? "✓ Copied!" : "Copy key"}
            </button>
            <button className="secondary" onClick={() => setIssuedKey(null)}>Dismiss</button>
          </div>
        </div>
      )}
      <div className="btn-row" style={{ marginBottom: 14 }}>
        <button onClick={issueKey} disabled={busy}>
          {busy ? <><span className="spinner" />Issuing…</> : "+ Issue key"}
        </button>
      </div>
      <table>
        <thead>
          <tr>
            <th>Prefix</th><th>Label</th><th>Status</th><th>Last used</th><th>Created</th><th></th>
          </tr>
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
            <tr key={k.id}>
              <td><code>{k.key_prefix}…</code></td>
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

      <Modal
        open={!!revokeTarget}
        title="Revoke API key"
        confirmLabel="Revoke"
        danger
        busy={busy}
        onConfirm={confirmRevoke}
        onClose={() => setRevokeTarget(null)}
      >
        {activeCount === 1
          ? "This is the client's last active key. Revoking it will lock them out immediately."
          : `Revoke key ${revokeTarget?.key_prefix}…? The client will lose access with this key immediately.`}
      </Modal>
    </div>
  );
}

// ── Config tab ────────────────────────────────────────────────────────────────

function ConfigTab({ clientId }: { clientId: string }) {
  const [config, setConfig] = useState<ClientConfig | null>(null);
  const [draft, setDraft] = useState<Partial<ClientConfig>>({});
  const [settingsValid, setSettingsValid] = useState(true);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [clearApiKey, setClearApiKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    adminApi.getConfig(clientId).then((c) => {
      setConfig(c);
      setDraft(c);
    }).catch((e) => setError(e.message));
  }, [clientId]);

  async function save() {
    if (!settingsValid) return;
    setBusy(true);
    setSaved(false);
    try {
      const payload: Partial<ClientConfig> = { ...draft };
      if (clearApiKey) {
        payload.analysis_llm_api_key = null;
      } else if (apiKeyInput.trim()) {
        payload.analysis_llm_api_key = apiKeyInput.trim();
      }
      delete payload.analysis_llm_api_key_set;
      const updated = await adminApi.updateConfig(clientId, payload);
      setConfig(updated);
      setDraft(updated);
      setApiKeyInput("");
      setClearApiKey(false);
      setSaved(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 580 }}>
      {error && <div className="error-box">{error}</div>}
      {saved && <div style={successStyle}>✓ Config saved.</div>}

      <div className="card">
        <h2>Call settings</h2>
        <div>
          <label>Default from number</label>
          <input type="text" value={draft.default_from_number ?? ""} placeholder="+1234567890"
            onChange={(e) => setDraft({ ...draft, default_from_number: e.target.value || null })} />
        </div>
        <div>
          <label>Webhook URL</label>
          <input type="url" value={draft.webhook_url ?? ""} placeholder="https://…"
            onChange={(e) => setDraft({ ...draft, webhook_url: e.target.value || null })} />
        </div>
        <JsonField
          label="Settings (JSON)"
          value={config?.settings ?? null}
          onChange={(parsed, valid) => { setDraft({ ...draft, settings: parsed as Record<string, unknown> | null }); setSettingsValid(valid); }}
        />
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>LLM analysis config</h2>
        <p className="hint" style={{ marginTop: 0 }}>
          Overrides system-level LLM defaults for this client's call analysis.
        </p>
        <div className="row">
          <div>
            <label>Provider</label>
            <select
              value={draft.analysis_llm_provider ?? ""}
              onChange={(e) => setDraft({ ...draft, analysis_llm_provider: e.target.value || null })}
            >
              <option value="">System default</option>
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
            </select>
          </div>
          <div>
            <label>Model</label>
            <input
              type="text"
              value={draft.analysis_llm_model ?? ""}
              placeholder="System default"
              onChange={(e) => setDraft({ ...draft, analysis_llm_model: e.target.value || null })}
            />
          </div>
        </div>
        <div>
          <label>Prompt hint (appended to system prompt)</label>
          <textarea
            value={draft.analysis_prompt_hint ?? ""}
            placeholder="Optional context for the LLM classifier…"
            rows={3}
            onChange={(e) => setDraft({ ...draft, analysis_prompt_hint: e.target.value || null })}
          />
        </div>
        <div>
          <label>
            API key{" "}
            <span className={`badge ${config?.analysis_llm_api_key_set ? "ok" : "warn"}`} style={{ fontSize: 11, verticalAlign: "middle" }}>
              {config?.analysis_llm_api_key_set ? "set" : "not set"}
            </span>
          </label>
          {clearApiKey ? (
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className="muted" style={{ fontSize: 13 }}>Key will be cleared on save.</span>
              <button className="secondary" style={{ fontSize: 12, padding: "4px 10px" }}
                onClick={() => setClearApiKey(false)}>Cancel</button>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <input
                type="password"
                value={apiKeyInput}
                placeholder={config?.analysis_llm_api_key_set ? "Enter new key to replace" : "Enter API key"}
                style={{ flex: 1, minWidth: 200 }}
                onChange={(e) => setApiKeyInput(e.target.value)}
                autoComplete="off"
              />
              {config?.analysis_llm_api_key_set && (
                <button className="danger" style={{ fontSize: 12, padding: "4px 10px", whiteSpace: "nowrap" }}
                  onClick={() => { setClearApiKey(true); setApiKeyInput(""); }}>
                  Clear key
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <button onClick={save} disabled={busy || !settingsValid}>
          {busy ? <><span className="spinner" />Saving…</> : "Save config"}
        </button>
      </div>
    </div>
  );
}

// ── Agents tab ────────────────────────────────────────────────────────────────

function AgentsTab({ clientId }: { clientId: string }) {
  const [catalog, setCatalog] = useState<CatalogAgent[]>([]);
  const [clientAgents, setClientAgents] = useState<ClientAgent[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [varSchema, setVarSchema] = useState<Record<string, AgentVariables>>({});
  const [pending, setPending] = useState<Record<string, { display_name: string; overrides: Record<string, string> }>>({});
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    Promise.all([adminApi.listCatalogAgents(), adminApi.getClientAgents(clientId)]).then(
      ([cat, cli]) => {
        setCatalog(cat);
        setClientAgents(cli);
        const enabledSet = new Set(cli.filter((c) => c.enabled).map((c) => c.voice_agent_id));
        setEnabled(enabledSet);
        const p: typeof pending = {};
        cli.forEach((c) => {
          p[c.voice_agent_id] = {
            display_name: c.display_name ?? "",
            overrides: c.variable_overrides ?? {},
          };
        });
        setPending(p);
      }
    ).catch((e) => setError(e.message));
  }, [clientId]);

  async function expandAgent(agentId: string) {
    if (expanded === agentId) { setExpanded(null); return; }
    setExpanded(agentId);
    if (!varSchema[agentId]) {
      try {
        const schema = await adminApi.getAgentVariables(agentId);
        setVarSchema((prev) => ({ ...prev, [agentId]: schema }));
      } catch {
        // non-fatal
      }
    }
  }

  function toggleEnabled(agentId: string) {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(agentId)) next.delete(agentId); else next.add(agentId);
      return next;
    });
  }

  async function saveEnabled() {
    setBusy(true);
    setSaved(false);
    try {
      await adminApi.setClientAgents(clientId, [...enabled]);
      setSaved(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function saveAgentConfig(agentId: string) {
    const p = pending[agentId];
    if (!p) return;
    setBusy(true);
    try {
      await adminApi.patchClientAgent(clientId, agentId, {
        display_name: p.display_name || undefined,
        variable_overrides: Object.keys(p.overrides).length > 0 ? p.overrides : undefined,
      });
      setSaved(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  function initPending(agentId: string) {
    if (!pending[agentId]) {
      const existing = clientAgents.find((c) => c.voice_agent_id === agentId);
      setPending((prev) => ({
        ...prev,
        [agentId]: { display_name: existing?.display_name ?? "", overrides: existing?.variable_overrides ?? {} },
      }));
    }
  }

  const allAgentIds = new Set(catalog.map((c) => c.voice_agent_id));
  const drifted = clientAgents.filter((ca) => !allAgentIds.has(ca.voice_agent_id));

  return (
    <div>
      {error && <div className="error-box">{error}</div>}
      {saved && <div style={successStyle}>✓ Saved.</div>}

      {drifted.length > 0 && (
        <div className="card" style={{ marginBottom: 16, borderColor: "var(--amber)", background: "rgba(245,181,68,0.06)" }}>
          <p style={{ margin: 0, fontSize: 13 }}>
            <span className="badge warn">Drifted</span>{" "}
            {drifted.length} agent(s) no longer exist upstream: {drifted.map((d) => d.voice_agent_id).join(", ")}
          </p>
        </div>
      )}

      <table>
        <thead>
          <tr><th>Agent</th><th>Status</th><th>Enabled</th><th></th></tr>
        </thead>
        <tbody>
          {catalog.map((agent) => {
            const isEnabled = enabled.has(agent.voice_agent_id);
            const isExpanded = expanded === agent.voice_agent_id;
            const p = pending[agent.voice_agent_id] ?? { display_name: "", overrides: {} };
            const schema = varSchema[agent.voice_agent_id];

            return (
              <>
                <tr key={agent.voice_agent_id}>
                  <td>
                    <div style={{ fontWeight: 500 }}>{agent.agent_name ?? agent.voice_agent_id}</div>
                    <div className="muted" style={{ fontSize: 11 }}>{agent.voice_agent_id}</div>
                  </td>
                  <td>
                    {!agent.is_present
                      ? <span className="badge warn">missing upstream</span>
                      : agent.agent_status === "active"
                      ? <span className="badge ok">active</span>
                      : <span className="badge err">{agent.agent_status}</span>}
                  </td>
                  <td>
                    <input type="checkbox" checked={isEnabled} onChange={() => toggleEnabled(agent.voice_agent_id)} />
                  </td>
                  <td>
                    {isEnabled && (
                      <button className="secondary" style={{ fontSize: 12, padding: "4px 10px" }}
                        onClick={() => { initPending(agent.voice_agent_id); expandAgent(agent.voice_agent_id); }}>
                        {isExpanded ? "▲ Close" : "▼ Configure"}
                      </button>
                    )}
                  </td>
                </tr>
                {isExpanded && (
                  <tr key={`${agent.voice_agent_id}-detail`}>
                    <td colSpan={4} style={{ padding: "4px 0 8px" }}>
                      <div className="agent-row-detail" style={{ animation: "page-in 0.25s var(--ease-glass)" }}>
                        <div>
                          <label>Display name</label>
                          <input type="text" value={p.display_name} placeholder={agent.agent_name ?? agent.voice_agent_id}
                            onChange={(e) => setPending((prev) => ({ ...prev, [agent.voice_agent_id]: { ...p, display_name: e.target.value } }))} />
                        </div>
                        {schema ? (
                          <AgentVariableForm
                            schema={schema}
                            overrides={p.overrides}
                            onChange={(overrides) => setPending((prev) => ({ ...prev, [agent.voice_agent_id]: { ...p, overrides } }))}
                          />
                        ) : (
                          <p className="muted" style={{ fontSize: 12 }}><span className="spinner" />Loading variable schema…</p>
                        )}
                        <button onClick={() => saveAgentConfig(agent.voice_agent_id)} disabled={busy} style={{ marginTop: 8 }}>
                          {busy ? <><span className="spinner" />Saving…</> : "Save agent config"}
                        </button>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            );
          })}
        </tbody>
      </table>

      <div className="btn-row" style={{ marginTop: 16 }}>
        <button onClick={saveEnabled} disabled={busy}>
          {busy ? <><span className="spinner" />Saving…</> : "Save enabled agents"}
        </button>
      </div>
    </div>
  );
}

// ── Phone Numbers tab ─────────────────────────────────────────────────────────

function PhoneNumbersTab({ clientId }: { clientId: string }) {
  const [catalog, setCatalog] = useState<PhoneNumberCatalogEntry[]>([]);
  const [assigned, setAssigned] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      adminApi.listPhoneNumberCatalog(),
      adminApi.getClientPhoneNumbers(clientId),
    ]).then(([cat, cli]) => {
      setCatalog(cat);
      setAssigned(new Set(cli.map((e: ClientPhoneNumberEntry) => e.id)));
    }).catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, [clientId]);

  function toggle(id: string) {
    setAssigned((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function save() {
    setBusy(true);
    setSaved(false);
    try {
      await adminApi.setClientPhoneNumbers(clientId, [...assigned]);
      setSaved(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  if (catalog.length === 0) {
    return (
      <div className="empty-state">
        No phone numbers in catalog. Go to <strong>Phone Numbers</strong> in the sidebar and run a sync first.
      </div>
    );
  }

  return (
    <div>
      {error && <div className="error-box">{error}</div>}
      {saved && <div style={successStyle}>✓ Saved.</div>}
      <table>
        <thead>
          <tr><th>Number</th><th>Provider</th><th>Rented</th><th>Present</th><th>Assigned</th></tr>
        </thead>
        <tbody>
          {catalog.map((n) => (
            <tr key={n.id}>
              <td>
                <span className="badge warn" style={{ fontFamily: "ui-monospace, monospace", letterSpacing: 0 }}>
                  {n.phone_number}
                </span>
              </td>
              <td className="muted">{n.telephony_provider ?? "—"}</td>
              <td className="muted">{n.rented != null ? (n.rented ? "yes" : "no") : "—"}</td>
              <td>
                {n.is_present
                  ? <span className="badge ok">yes</span>
                  : <span className="badge err">missing</span>}
              </td>
              <td>
                <input type="checkbox" checked={assigned.has(n.id)} onChange={() => toggle(n.id)} disabled={!n.is_present} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="btn-row" style={{ marginTop: 16 }}>
        <button onClick={save} disabled={busy}>
          {busy ? <><span className="spinner" />Saving…</> : "Save assigned numbers"}
        </button>
      </div>
    </div>
  );
}

// ── Drift tab ─────────────────────────────────────────────────────────────────

function DriftTab({ clientId }: { clientId: string }) {
  const [events, setEvents] = useState<DriftEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    adminApi.getDrift(clientId).then(setEvents).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, [clientId]);

  useEffect(() => { reload(); }, [reload]);

  async function acknowledge(eventId: string) {
    setBusy(true);
    try {
      await adminApi.acknowledgeDrift(clientId, eventId);
      reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {error && <div className="error-box">{error}</div>}
      {!loading && events.length === 0 ? (
        <div className="empty-state">No drift events — all agents are in sync.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {loading && (
            <>
              {[0, 1].map((i) => (
                <div key={i} className="card" style={{ padding: 14 }}>
                  <div className="skeleton skeleton-row w-60" style={{ height: 12 }} />
                  <div className="skeleton skeleton-row w-40" style={{ height: 12 }} />
                </div>
              ))}
            </>
          )}
          {events.map((ev) => (
            <div key={ev.id} className="card" style={{
              borderLeft: ev.acknowledged ? "3px solid var(--glass-border)" : "3px solid var(--amber)",
              padding: "12px 16px",
            }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                <div>
                  <code style={{ fontSize: 12 }}>{ev.voice_agent_id}</code>{" "}
                  <span className="badge warn">{ev.event_type}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span className="muted" style={{ fontSize: 12 }}>{new Date(ev.created_at).toLocaleString()}</span>
                  {ev.acknowledged
                    ? <span className="badge ok">acknowledged</span>
                    : (
                      <button className="secondary" style={{ fontSize: 12, padding: "4px 10px" }}
                        onClick={() => acknowledge(ev.id)} disabled={busy}>
                        {busy ? <span className="spinner" /> : null}
                        Acknowledge
                      </button>
                    )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ClientDetailPage() {
  const params = useParams();
  const router = useRouter();
  const clientId = params.id as string;

  const [client, setClient] = useState<ClientSummary | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [approveResult, setApproveResult] = useState<ApproveResult | null>(null);
  const [confirmAction, setConfirmAction] = useState<null | { label: string; action: string; danger: boolean }>(null);

  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const reload = useCallback(() => {
    adminApi.getClient(clientId).then(setClient).catch((e) => setError(e.message));
  }, [clientId]);

  useEffect(() => { reload(); }, [reload]);

  function startEdit() {
    if (!client) return;
    setEditName(client.name);
    setEditEmail(client.contact_email ?? "");
    setEditError(null);
    setEditing(true);
  }

  async function saveEdit() {
    setEditBusy(true);
    setEditError(null);
    try {
      const updated = await adminApi.updateClient(clientId, {
        name: editName.trim() || undefined,
        contact_email: editEmail.trim() || null,
      });
      setClient(updated);
      setEditing(false);
    } catch (e: unknown) {
      setEditError(e instanceof Error ? e.message : "Failed");
    } finally {
      setEditBusy(false);
    }
  }

  async function runAction(action: string) {
    setBusy(true);
    setError(null);
    try {
      switch (action) {
        case "approve": {
          const result = await adminApi.approve(clientId);
          setApproveResult(result);
          break;
        }
        case "reject":   await adminApi.reject(clientId); break;
        case "suspend":  await adminApi.suspend(clientId); break;
        case "reactivate": await adminApi.reactivate(clientId); break;
        case "delete":
          await adminApi.deleteClient(clientId);
          router.push("/clients");
          return;
      }
      reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
      setConfirmAction(null);
    }
  }

  const TABS: { key: Tab; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "keys", label: "API Keys" },
    { key: "config", label: "Config" },
    { key: "agents", label: "Agents" },
    { key: "phone-numbers", label: "Phone Numbers" },
    { key: "drift", label: "Drift" },
  ];

  const lifecycleButtons = (() => {
    if (!client) return null;
    const s = client.status;
    return (
      <div className="btn-row">
        {(s === "pending" || s === "rejected") && (
          <button onClick={() => setConfirmAction({ label: "Approve", action: "approve", danger: false })} disabled={busy}>
            Approve
          </button>
        )}
        {s === "pending" && (
          <button className="secondary" onClick={() => setConfirmAction({ label: "Reject", action: "reject", danger: true })} disabled={busy}>
            Reject
          </button>
        )}
        {s === "active" && (
          <button className="danger" onClick={() => setConfirmAction({ label: "Suspend", action: "suspend", danger: true })} disabled={busy}>
            Suspend
          </button>
        )}
        {s === "suspended" && (
          <button onClick={() => setConfirmAction({ label: "Reactivate", action: "reactivate", danger: false })} disabled={busy}>
            Reactivate
          </button>
        )}
        <button
          className="danger"
          style={{ marginLeft: "auto" }}
          onClick={() => setConfirmAction({ label: "Delete", action: "delete", danger: true })}
          disabled={busy}
        >
          Delete client
        </button>
      </div>
    );
  })();

  return (
    <div className="page-enter">
      {error && <div className="error-box">{error}</div>}

      {approveResult && (
        <div style={{
          background: "rgba(55,201,120,0.08)",
          border: "1px solid rgba(55,201,120,0.35)",
          borderRadius: "var(--radius)",
          padding: 20,
          marginBottom: 20,
          animation: "page-in 0.3s var(--ease-glass)",
        }}>
          <p style={{ margin: "0 0 8px", fontWeight: 600, color: "var(--green)" }}>✓ Client approved. Initial API key:</p>
          <pre className="key-reveal">{approveResult.api_key}</pre>
          {approveResult.claim_url && (
            <p style={{ margin: "10px 0 0", fontSize: 13 }}>
              Claim link:{" "}
              <a href={approveResult.claim_url} style={{ color: "var(--accent)" }}>
                {approveResult.claim_url}
              </a>
            </p>
          )}
          <button className="secondary" style={{ marginTop: 10 }} onClick={() => setApproveResult(null)}>Dismiss</button>
        </div>
      )}

      {client ? (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6, flexWrap: "wrap" }}>
            <h1 style={{ margin: 0 }}>{client.name}</h1>
            <StatusBadge status={client.status} />
          </div>
          <p className="subtitle">{client.slug} · {client.contact_email ?? "no email"}</p>
          {lifecycleButtons}
          <div style={{ height: 24 }} />
        </>
      ) : (
        <div>
          <div className="skeleton skeleton-row w-60" style={{ height: 28, marginBottom: 8 }} />
          <div className="skeleton skeleton-row w-40" style={{ height: 14, marginBottom: 24 }} />
        </div>
      )}

      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {client && (
        <>
          {tab === "overview" && (
            <div className="card" style={{ maxWidth: 480 }}>
              {editError && <div className="error-box" style={{ marginBottom: 12 }}>{editError}</div>}
              {editing ? (
                <div>
                  <div>
                    <label>Name</label>
                    <input value={editName} onChange={(e) => setEditName(e.target.value)} disabled={editBusy} />
                  </div>
                  <div>
                    <label>Contact email</label>
                    <input type="email" value={editEmail} onChange={(e) => setEditEmail(e.target.value)} placeholder="— clear to remove —" disabled={editBusy} />
                  </div>
                  <div className="btn-row" style={{ marginTop: 12 }}>
                    <button onClick={saveEdit} disabled={editBusy || !editName.trim()}>
                      {editBusy ? <><span className="spinner" />Saving…</> : "Save"}
                    </button>
                    <button className="secondary" onClick={() => setEditing(false)} disabled={editBusy}>Cancel</button>
                  </div>
                </div>
              ) : (
                <>
                  <table>
                    <tbody>
                      <tr><td className="muted" style={{ width: 140 }}>ID</td><td><code style={{ fontSize: 12 }}>{client.id}</code></td></tr>
                      <tr><td className="muted">Status</td><td><StatusBadge status={client.status} /></td></tr>
                      <tr><td className="muted">Registered</td><td>{new Date(client.created_at).toLocaleString()}</td></tr>
                      <tr><td className="muted">Approved</td><td>{client.approved_at ? new Date(client.approved_at).toLocaleString() : "—"}</td></tr>
                      <tr><td className="muted">Email</td><td>{client.contact_email ?? "—"}</td></tr>
                    </tbody>
                  </table>
                  <button className="secondary" style={{ marginTop: 14, fontSize: 13 }} onClick={startEdit}>Edit details</button>
                </>
              )}
            </div>
          )}
          {tab === "keys" && <KeysTab clientId={clientId} />}
          {tab === "config" && <ConfigTab clientId={clientId} />}
          {tab === "agents" && <AgentsTab clientId={clientId} />}
          {tab === "phone-numbers" && <PhoneNumbersTab clientId={clientId} />}
          {tab === "drift" && <DriftTab clientId={clientId} />}
        </>
      )}

      <Modal
        open={!!confirmAction}
        title={`${confirmAction?.label} client?`}
        confirmLabel={confirmAction?.label}
        danger={confirmAction?.danger}
        busy={busy}
        onConfirm={() => confirmAction && runAction(confirmAction.action)}
        onClose={() => setConfirmAction(null)}
      >
        Are you sure you want to {confirmAction?.label.toLowerCase()} <strong>{client?.name}</strong>?
      </Modal>
    </div>
  );
}
