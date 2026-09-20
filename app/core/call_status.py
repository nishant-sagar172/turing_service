"""Single source of truth for call-status vocabulary.

``app/services/store.py`` and ``app/services/analytics.py`` both re-export
these frozensets under their historical names (``TERMINAL_STATUSES`` /
``_SUCCESS_STATUSES`` in store; ``CONNECTED`` / ``NOT_CONNECTED`` / ``TERMINAL``
in analytics) so existing importers — ``app/routers/calls.py`` and
``app/routers/webhooks.py`` — keep working unchanged.
"""

from __future__ import annotations

CONNECTED_STATUSES: frozenset[str] = frozenset({"completed"})
NOT_CONNECTED_STATUSES: frozenset[str] = frozenset(
    {
        "no-answer",
        "busy",
        "failed",
        "canceled",
        "cancelled",
        "stopped",
        "error",
        "balance-low",
    }
)
TERMINAL_STATUSES: frozenset[str] = CONNECTED_STATUSES | NOT_CONNECTED_STATUSES

# Batch-level vocabulary — distinct from the call-level statuses above (see
# app/routers/webhooks.py::BATCH_TERMINAL_STATUSES, which stays the live copy
# until the router is migrated to import from here).
BATCH_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "stopped", "failed", "cancelled", "canceled"}
)


def normalize_batch_status(raw: str | None) -> str | None:
    """Reduce the voice engine's batch state to a bare status token.

    Bolna reports a scheduled batch as ``"scheduled at 2026-09-15T14:16:00+00:00"``
    — a status with the timestamp glued on. Stored verbatim that value never
    equals ``"scheduled"``, so anything filtering on status silently skips the
    batch. Only the leading token is kept; the schedule itself already lives in
    ``Batch.scheduled_at``.
    """
    if raw is None:
        return None
    return raw.split(" at ", 1)[0].strip() or None
