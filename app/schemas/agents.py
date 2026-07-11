"""Schemas for the /agents endpoint (agent-picker dropdown source)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AgentSummary(BaseModel):
    """A Bolna agent, trimmed to what a picker needs. Extra fields preserved."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    agent_name: str | None = None
    agent_type: str | None = None
    agent_status: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AgentVariables(BaseModel):
    """Variables an agent's prompt references (discovered read-only from Bolna).

    Callers must supply every ``required`` variable; ``optional`` ones may be
    omitted; ``system_injected`` are provided automatically by Bolna and must
    not be sent.
    """

    agent_id: str
    required: list[str] = []
    optional: list[str] = []
    system_injected: list[str] = []
    all_prompt_variables: list[str] = []
