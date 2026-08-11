"use client";

import { useState } from "react";

interface Props {
  label: string;
  value: Record<string, unknown> | null | undefined;
  onChange: (parsed: Record<string, unknown> | null, valid: boolean) => void;
  rows?: number;
}

export default function JsonField({ label, value, onChange, rows = 4 }: Props) {
  const [raw, setRaw] = useState(() =>
    value != null ? JSON.stringify(value, null, 2) : ""
  );
  const [error, setError] = useState<string | null>(null);

  function handleChange(text: string) {
    setRaw(text);
    if (text.trim() === "") {
      setError(null);
      onChange(null, true);
      return;
    }
    try {
      const parsed = JSON.parse(text);
      setError(null);
      onChange(parsed, true);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Invalid JSON";
      setError(msg);
      onChange(null, false);
    }
  }

  return (
    <div>
      <label>{label}</label>
      <textarea
        rows={rows}
        value={raw}
        onChange={(e) => handleChange(e.target.value)}
        placeholder="{}"
        style={{ fontFamily: "ui-monospace, monospace", fontSize: 12.5 }}
      />
      {error && <p className="hint" style={{ color: "var(--red)" }}>{error}</p>}
    </div>
  );
}
