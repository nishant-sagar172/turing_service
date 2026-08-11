"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { adminApi } from "../../../lib/adminApi";
import Modal from "../../../components/Modal";
import type { ClientSummary } from "../../../lib/types";

const STATUS_FILTERS = ["all", "pending", "active", "suspended", "rejected"];

function statusBadge(s: string) {
  const cls =
    s === "active" ? "ok" : s === "pending" ? "warn" : s === "suspended" ? "warn" : "err";
  return <span className={`badge ${cls}`}>{s}</span>;
}

export default function ClientsPage() {
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newStatus, setNewStatus] = useState<"pending" | "active">("pending");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [editTarget, setEditTarget] = useState<ClientSummary | null>(null);
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editing, setEditing] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  function reload() {
    setLoading(true);
    adminApi
      .listClients(filter === "all" ? undefined : filter)
      .then(setClients)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed"))
      .finally(() => setLoading(false));
  }

  useEffect(() => { reload(); }, [filter]);

  async function create() {
    setCreating(true);
    setCreateError(null);
    try {
      await adminApi.createClient(newName.trim(), newEmail.trim() || undefined, newStatus);
      setShowCreate(false);
      setNewName("");
      setNewEmail("");
      setNewStatus("pending");
      reload();
    } catch (e: unknown) {
      setCreateError(e instanceof Error ? e.message : "Failed");
    } finally {
      setCreating(false);
    }
  }

  function openEdit(c: ClientSummary) {
    setEditTarget(c);
    setEditName(c.name);
    setEditEmail(c.contact_email ?? "");
    setEditError(null);
  }

  async function saveEdit() {
    if (!editTarget) return;
    setEditing(true);
    setEditError(null);
    try {
      const trimmedEmail = editEmail.trim();
      await adminApi.updateClient(editTarget.id, {
        name: editName.trim(),
        contact_email: trimmedEmail === "" ? null : trimmedEmail,
      });
      setEditTarget(null);
      reload();
    } catch (e: unknown) {
      setEditError(e instanceof Error ? e.message : "Failed");
    } finally {
      setEditing(false);
    }
  }

  return (
    <div className="page-enter">
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 4 }}>
        <h1>Clients</h1>
        <button className="clients-desktop-btn" onClick={() => setShowCreate(true)}>
          + New client
        </button>
      </div>
      <p className="subtitle">Registered tenants and their onboarding status.</p>

      <div className="filter-strip">
        {STATUS_FILTERS.map((f) => (
          <button key={f} className={filter === f ? "active" : ""} onClick={() => setFilter(f)}>
            {f}
          </button>
        ))}
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Slug</th>
              <th>Email</th>
              <th>Status</th>
              <th>Registered</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <>
                {[0, 1, 2].map((i) => (
                  <tr key={i}>
                    {[80, 60, 80, 40, 60, 40].map((w, j) => (
                      <td key={j}>
                        <div className={`skeleton skeleton-row w-${w}`} style={{ height: 12, margin: 0 }} />
                      </td>
                    ))}
                  </tr>
                ))}
              </>
            )}
            {!loading && clients.length === 0 && (
              <tr>
                <td colSpan={6} style={{ padding: 0 }}>
                  <div className="empty-state">No clients match this filter.</div>
                </td>
              </tr>
            )}
            {clients.map((c) => (
              <tr key={c.id}>
                <td style={{ fontWeight: 500 }}>{c.name}</td>
                <td className="muted">{c.slug}</td>
                <td className="muted">{c.contact_email ?? "—"}</td>
                <td>{statusBadge(c.status)}</td>
                <td className="muted">{new Date(c.created_at).toLocaleDateString()}</td>
                <td>
                  <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                    <button
                      className="secondary"
                      title="Edit client"
                      style={{ padding: "4px 8px", minWidth: "auto" }}
                      onClick={() => openEdit(c)}
                    >
                      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ display: "block" }}>
                        <path d="M11.013 1.427a1.75 1.75 0 0 1 2.474 2.474l-.613.613-2.474-2.474.613-.613ZM9.513 3.34 2.25 10.603V13h2.397l7.263-7.263-2.397-2.397Z" fill="currentColor" />
                      </svg>
                    </button>
                    <Link
                      href={`/clients/${c.id}`}
                      style={{
                        display: "inline-block",
                        padding: "4px 10px",
                        borderRadius: 6,
                        fontSize: 12,
                        fontWeight: 600,
                        background: "var(--glass-bg)",
                        border: "1px solid var(--glass-border)",
                        color: "var(--accent)",
                        transition: "all var(--duration-fast) var(--ease-glass)",
                      }}
                    >
                      Manage →
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile FAB */}
      <button className="fab" onClick={() => setShowCreate(true)} aria-label="New client">+</button>

      {/* Create modal */}
      <Modal
        open={showCreate}
        title="New client"
        confirmLabel="Create"
        busy={creating}
        onConfirm={create}
        onClose={() => { setShowCreate(false); setCreateError(null); }}
      >
        {createError && <div className="error-box" style={{ marginBottom: 12 }}>{createError}</div>}
        <div>
          <label>Organization name *</label>
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Acme Health"
            disabled={creating}
          />
        </div>
        <div>
          <label>Contact email</label>
          <input
            type="email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            placeholder="ops@example.com"
            disabled={creating}
          />
        </div>
        <div>
          <label>Initial status</label>
          <select value={newStatus} onChange={(e) => setNewStatus(e.target.value as "pending" | "active")} disabled={creating}>
            <option value="pending">pending — requires approval</option>
            <option value="active">active — skip approval</option>
          </select>
        </div>
      </Modal>

      {/* Edit modal */}
      <Modal
        open={!!editTarget}
        title={`Edit — ${editTarget?.name}`}
        confirmLabel="Save"
        busy={editing}
        onConfirm={saveEdit}
        onClose={() => { setEditTarget(null); setEditError(null); }}
      >
        {editError && <div className="error-box" style={{ marginBottom: 12 }}>{editError}</div>}
        <div>
          <label>Organization name *</label>
          <input
            type="text"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            disabled={editing}
          />
        </div>
        <div>
          <label>Contact email</label>
          <input
            type="email"
            value={editEmail}
            onChange={(e) => setEditEmail(e.target.value)}
            placeholder="— leave empty to clear —"
            disabled={editing}
          />
        </div>
      </Modal>
    </div>
  );
}
