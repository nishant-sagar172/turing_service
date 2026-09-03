"""Offline allowlist generator for a workspace's target DB (plan §Files).

Introspects the target DB READ-ONLY and structurally (no data rows — see
``ingestion.introspect``) and writes the committed snapshot
``app/sql_agent/workspaces/<workspace>.allowlist.json``: the authoritative
``{table: [columns]}`` trust set the deterministic guard walks candidate SQL
against. Covers *every* real column, not just the enriched subset, so a
valid-but-unenriched column is never falsely rejected.

Run whenever the target schema changes:

    python -m app.sql_agent.gen_allowlist --workspace kalaam

Requires the workspace's read-only URL in the environment (e.g.
``KALAAM_READONLY_DATABASE_URL``). Table + column names are lowercased,
unqualified (default schema only), and sorted so the artifact diffs cleanly.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from app.sql_agent.ingestion.introspect import introspect_target, workspace_env_var
from app.sql_agent.ingestion.loader import WORKSPACES_DIR, load_workspace_file


def allowlist_path(workspace: str, workspaces_dir: Path = WORKSPACES_DIR) -> Path:
    """Path of the committed allowlist snapshot for a workspace."""
    return workspaces_dir / f"{workspace}.allowlist.json"


async def build_allowlist(workspace: str) -> dict[str, object]:
    """Introspect the target DB and build the allowlist document (in memory).

    Only the datasource's default schema is included; names are lowercased and
    unqualified, columns sorted, tables sorted — deterministic output.
    """
    spec = load_workspace_file(workspace)
    default_schema = spec.datasource.default_schema
    result = await introspect_target(workspace_env_var(workspace))

    tables: dict[str, list[str]] = {}
    for table in result.tables:
        if table.schema_name != default_schema:
            continue
        columns = sorted({column.column_name.lower() for column in table.columns})
        tables[table.table_name.lower()] = columns

    if not tables:
        raise RuntimeError(
            f"introspection returned no tables in default schema "
            f"{default_schema!r} for workspace {workspace!r}; refusing to write "
            "an empty allowlist (fail closed)"
        )

    return {
        "workspace": workspace,
        "dialect": spec.datasource.dialect,
        "generated_from": "introspection",
        "tables": dict(sorted(tables.items())),
    }


def write_allowlist(workspace: str, document: dict[str, object]) -> Path:
    """Write the allowlist document to its committed path; return the path."""
    path = allowlist_path(workspace)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the committed column allowlist for a workspace's "
        "target DB (read-only structural introspection)."
    )
    parser.add_argument(
        "--workspace", required=True, help="Workspace slug, e.g. kalaam"
    )
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    document = asyncio.run(build_allowlist(args.workspace))
    path = write_allowlist(args.workspace, document)

    tables = document["tables"]
    assert isinstance(tables, dict)
    total_columns = sum(len(columns) for columns in tables.values())
    print(f"WROTE {path}")
    print(f"  workspace:     {document['workspace']}")
    print(f"  dialect:       {document['dialect']}")
    print(f"  generated_from:{document['generated_from']}")
    print(f"  tables:        {len(tables)}")
    print(f"  columns:       {total_columns}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
