"use client";

import type { AgentVariables } from "../lib/types";

interface Props {
  schema: AgentVariables;
  overrides: Record<string, string>;
  onChange: (overrides: Record<string, string>) => void;
}

export default function AgentVariableForm({ schema, overrides, onChange }: Props) {
  const editable = [...schema.required, ...schema.optional].filter(
    (v) => !schema.system_injected.includes(v)
  );

  if (editable.length === 0) {
    return <p className="muted" style={{ fontSize: 12 }}>No configurable variables for this agent.</p>;
  }

  function set(key: string, val: string) {
    const next = { ...overrides };
    if (val === "") {
      delete next[key];
    } else {
      next[key] = val;
    }
    onChange(next);
  }

  return (
    <div>
      {editable.map((v) => (
        <div key={v}>
          <label>
            {v}
            {schema.required.includes(v) && (
              <span style={{ color: "var(--red)", marginLeft: 4 }}>*</span>
            )}
          </label>
          <input
            type="text"
            value={overrides[v] ?? ""}
            placeholder={schema.required.includes(v) ? "required" : "optional"}
            onChange={(e) => set(v, e.target.value)}
          />
        </div>
      ))}
      {schema.system_injected.length > 0 && (
        <p className="hint">
          System-injected (read-only): {schema.system_injected.join(", ")}
        </p>
      )}
    </div>
  );
}
