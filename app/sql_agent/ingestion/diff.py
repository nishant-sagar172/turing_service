"""Deterministic content-hash change detection for ingestion (plan §3).

Every ingested row gets a stable SHA-256 hash over its *content* fields — the
fields that affect what an embedding or a prompt would see. On re-ingestion,
rows whose hash is unchanged are skipped entirely (no UPDATE, and later no
re-embedding); changed rows are updated and their stale embedding is cleared.

Soft-delete semantics: rows present in the store but missing from a fresh
snapshot are classified ``removed``. For tables the caller must translate that
to ``is_active=false`` — never a hard DELETE — so historical audit rows stay
valid. Rows already inactive and still missing classify as ``unchanged`` so a
repeat run is a no-op.

Pure module: no DB access, no I/O — unit-testable with in-memory fixtures.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

# Bump when the hashing scheme itself changes: forces every row to classify as
# updated exactly once, instead of silently comparing incompatible hashes.
HASH_VERSION = "v1"

K = TypeVar("K")


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )


def content_hash(kind: str, payload: Mapping[str, Any]) -> str:
    """Stable hash of one row's content fields; ``kind`` namespaces entity types."""
    raw = f"{HASH_VERSION}:{kind}:{_canonical(payload)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def column_content_hash(
    *,
    column_name: str,
    data_type: str,
    is_nullable: bool,
    is_primary_key: bool,
    is_foreign_key: bool,
    description: str | None,
    is_sensitive: bool,
    sample_values: list[Any] | None,
) -> str:
    return content_hash(
        "column",
        {
            "column_name": column_name,
            "data_type": data_type,
            "is_nullable": is_nullable,
            "is_primary_key": is_primary_key,
            "is_foreign_key": is_foreign_key,
            "description": description,
            "is_sensitive": is_sensitive,
            "sample_values": sample_values,
        },
    )


def table_content_hash(
    *,
    schema_name: str,
    table_name: str,
    description: str | None,
    column_hashes: Iterable[str],
) -> str:
    """Table hash folds in its columns' hashes (sorted, so order never matters):
    a column-level change must re-embed the table, whose embedding text is
    built from the table description plus its column inventory.
    ``row_count_estimate`` is deliberately excluded — it drifts with data
    volume and must not churn hashes or trigger re-embedding.
    """
    return content_hash(
        "table",
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "description": description,
            "column_hashes": sorted(column_hashes),
        },
    )


def glossary_content_hash(
    *,
    term: str,
    definition: str,
    maps_to_table: str | None,
    maps_to_column: str | None,
) -> str:
    """Uses table/column *names*, not control-DB UUIDs — UUIDs differ across
    environments and would churn hashes for identical content."""
    return content_hash(
        "glossary",
        {
            "term": term,
            "definition": definition,
            "maps_to_table": maps_to_table,
            "maps_to_column": maps_to_column,
        },
    )


def example_content_hash(
    *,
    question: str,
    sql_text: str,
    tables_used: list[str] | None,
    is_verified: bool,
) -> str:
    return content_hash(
        "example",
        {
            "question": question,
            "sql_text": sql_text,
            "tables_used": tables_used,
            "is_verified": is_verified,
        },
    )


@dataclass(frozen=True)
class RowState:
    """What the store currently holds for one row, reduced to diff inputs."""

    content_hash: str | None
    is_active: bool = True


@dataclass(frozen=True)
class DiffResult(Generic[K]):
    """Classification of every row key across store + fresh snapshot.

    - ``created``: in fresh, not in store.
    - ``updated``: in both, but content hash differs — or the stored row is
      inactive and has reappeared (reactivation counts as an update).
    - ``unchanged``: in both with equal hash and active; or inactive in the
      store and still absent from fresh (soft-delete already applied).
    - ``removed``: active in the store but absent from fresh — the caller
      soft-deletes (tables) or deletes (rows without an is_active flag,
      where keeping a stale row would let the validator approve
      hallucinated references).
    """

    created: frozenset[K]
    updated: frozenset[K]
    unchanged: frozenset[K]
    removed: frozenset[K]

    @property
    def changed(self) -> bool:
        return bool(self.created or self.updated or self.removed)


def diff_rows(existing: Mapping[K, RowState], fresh: Mapping[K, str]) -> DiffResult[K]:
    """Classify ``fresh`` (key -> content hash) against ``existing`` row states."""
    created: set[K] = set()
    updated: set[K] = set()
    unchanged: set[K] = set()
    removed: set[K] = set()

    for key, fresh_hash in fresh.items():
        state = existing.get(key)
        if state is None:
            created.add(key)
        elif state.is_active and state.content_hash == fresh_hash:
            unchanged.add(key)
        else:
            updated.add(key)

    for key, state in existing.items():
        if key in fresh:
            continue
        if state.is_active:
            removed.add(key)
        else:
            unchanged.add(key)

    return DiffResult(
        created=frozenset(created),
        updated=frozenset(updated),
        unchanged=frozenset(unchanged),
        removed=frozenset(removed),
    )
