"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Agent } from "@/lib/types";

export default function AgentSelect({
  value,
  onChange,
  label = "Agent",
}: {
  value: string;
  onChange: (id: string) => void;
  label?: string;
}) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .agents()
      .then(setAgents)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <div>
      <label>{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">
          {error ? "Failed to load agents" : "Select an agent…"}
        </option>
        {agents.map((a, i) => (
          <option key={a.id || i} value={a.id || ""}>
            {a.agent_name || a.id}
            {a.agent_status ? ` · ${a.agent_status}` : ""}
          </option>
        ))}
      </select>
      {error && <p className="hint">{error}</p>}
    </div>
  );
}
