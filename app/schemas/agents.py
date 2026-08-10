from __future__ import annotations

from pydantic import BaseModel


class AgentSummary(BaseModel):
    id: str
    agent_name: str | None = None
    agent_status: str | None = None
    display_name: str | None = None


class AgentVariables(BaseModel):
    agent_id: str
    required: list[str] = []
    optional: list[str] = []
    system_injected: list[str] = []
    all_prompt_variables: list[str] = []
