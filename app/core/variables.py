"""Read-only introspection of an agent's variables.

We NEVER modify an agent. We only read its existing voice-engine config to
discover which ``{placeholder}`` variables its prompt already references, so
turing can validate that a caller supplied them before placing a call.

Voice-engine variable rules (from the Bolna docs):
- User variables use ``{variable_name}`` syntax inside the prompt.
- System variables are auto-injected by the engine and must NOT be treated as
  caller-supplied.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any

# Auto-injected by the voice engine; callers never provide these.
SYSTEM_VARIABLES: frozenset[str] = frozenset(
    {
        "agent_id",
        "execution_id",
        "call_sid",
        "from_number",
        "to_number",
        "current_date",
        "current_time",
        "timezone",
    }
)

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _iter_prompt_texts(agent: dict[str, Any]) -> list[str]:
    """Collect every prompt/welcome string in an agent config, defensively.

    Handles both the flat shape (agent_prompts at top level) and the nested
    shape (under agent_config).
    """
    texts: list[str] = []
    containers = [agent, agent.get("agent_config") or {}]
    for container in containers:
        if not isinstance(container, dict):
            continue
        welcome = container.get("agent_welcome_message")
        if isinstance(welcome, str):
            texts.append(welcome)
        prompts = container.get("agent_prompts")
        if isinstance(prompts, dict):
            for task in prompts.values():
                if isinstance(task, dict):
                    for value in task.values():
                        if isinstance(value, str):
                            texts.append(value)
                elif isinstance(task, str):
                    texts.append(task)
    return texts


def extract_prompt_variables(agent: dict[str, Any]) -> set[str]:
    """Return the set of user variables referenced in the agent's prompt(s)."""
    found: set[str] = set()
    for text in _iter_prompt_texts(agent):
        found.update(_PLACEHOLDER.findall(text))
    return found - set(SYSTEM_VARIABLES)


def load_variable_overrides(path: str) -> dict[str, Any]:
    """Load the per-agent override file. Returns {} if the file is absent.

    Cached on the file's identity stamp, so an operator editing the override
    file takes effect on the next call instead of requiring a process restart.

    The stamp is (mtime_ns, size): nanosecond mtime rather than the float from
    ``getmtime`` because two edits inside one filesystem timestamp tick would
    otherwise be indistinguishable, and size as a tiebreaker for that case.
    Two same-size edits within a single tick would still read stale — an
    inherent limit of stat-based invalidation, and harmless for a
    hand-maintained config file.
    """
    try:
        stat = os.stat(path)
    except OSError:
        # Missing/unreadable: fail safe to "no overrides", same as before.
        return {}
    return _load_variable_overrides_cached(path, stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=8)
def _load_variable_overrides_cached(
    path: str, _mtime_ns: int, _size: int
) -> dict[str, Any]:
    """Read and parse the override file. The stamp args are cache keys only."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        # Malformed file: fail safe to "no overrides" rather than crash.
        return {}


# Preserve the ``lru_cache`` surface the public name had before caching moved to
# the inner function — callers and tests rely on ``cache_clear()``.
load_variable_overrides.cache_clear = (  # type: ignore[attr-defined]
    _load_variable_overrides_cached.cache_clear
)


def resolve_agent_variables(
    agent: dict[str, Any], overrides: dict[str, Any] | None = None
) -> dict[str, list[str]]:
    """Split an agent's discovered variables into required vs optional.

    ``overrides`` is the entry for this agent from the override file, e.g.
    ``{"optional": ["nickname"]}``. Only variables actually present in the
    prompt can be marked optional.
    """
    discovered = extract_prompt_variables(agent)
    optional_marked = set((overrides or {}).get("optional", [])) & discovered
    required = sorted(discovered - optional_marked)
    return {
        "all_prompt_variables": sorted(discovered),
        "required": required,
        "optional": sorted(optional_marked),
        "system_injected": sorted(SYSTEM_VARIABLES),
    }


def validate_variables(
    provided: set[str], required: list[str], optional: list[str]
) -> tuple[list[str], list[str]]:
    """Return (missing_required, unrecognized_extra) for a set of provided keys."""
    missing = sorted(set(required) - provided)
    known = set(required) | set(optional)
    extra = sorted(provided - known)
    return missing, extra
