"use client";

import { useEffect } from "react";

interface Props {
  open: boolean;
  title: string;
  confirmLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
  children: React.ReactNode;
}

export default function Modal({
  open,
  title,
  confirmLabel = "Confirm",
  danger = false,
  busy = false,
  onConfirm,
  onClose,
  children,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const handle = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", handle);
    return () => document.removeEventListener("keydown", handle);
  }, [open, onClose]);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h2 style={{ margin: 0 }}>{title}</h2>
          <button
            className="secondary"
            onClick={onClose}
            disabled={busy}
            aria-label="Close"
            style={{ padding: "4px 10px", fontSize: 16, minWidth: "auto" }}
          >
            ✕
          </button>
        </div>
        <div style={{ marginBottom: 20, color: "var(--muted)", fontSize: 13 }}>{children}</div>
        <div className="btn-row" style={{ justifyContent: "flex-end" }}>
          <button className="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className={danger ? "danger" : ""} onClick={onConfirm} disabled={busy}>
            {busy ? <><span className="spinner" />Working…</> : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
