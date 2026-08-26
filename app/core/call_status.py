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
