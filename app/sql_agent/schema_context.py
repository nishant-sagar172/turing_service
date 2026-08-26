"""Cached schema context for the SQL Builder Agent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from collections.abc import Sequence
from typing import Mapping, cast

from app.sql_agent.gen_allowlist import allowlist_path
from app.sql_agent.ingestion.loader import (
    ColumnSpec,
    TableSpec,
    WORKSPACES_DIR,
    WorkspaceFile,
    load_workspace_file,
)
from app.sql_agent.validation.sql_guard import ColumnAllowlist


class SchemaContextError(RuntimeError):
    """Workspace schema context could not be loaded safely."""


@dataclass(frozen=True)
class SchemaCatalog:
    workspace: str
    dialect: str
    default_schema: str
    connection_env_var: str
    prompt_catalog: str
    table_specs: Mapping[str, TableSpec]
    table_contexts: Mapping[str, str]
    allowlist: ColumnAllowlist

    def summary(self) -> str:
        column_count = sum(len(columns) for columns in self.allowlist.values())
        return (
            f"workspace={self.workspace} dialect={self.dialect} "
            f"tables={len(self.allowlist)} columns={column_count}"
        )

    def render_table_subset(
        self,
        table_names: list[str],
        selected_columns: Mapping[str, Sequence[str]] | None = None,
    ) -> str:
        lines: list[str] = []
        for table_name in table_names:
            allowed_columns = self.allowlist.get(table_name)
            if allowed_columns is None:
                continue
            if selected_columns is not None:
                selected = {
                    column_name
                    for column_name in selected_columns.get(table_name, [])
                    if column_name in allowed_columns
                }
                allowed_columns = frozenset(selected) if selected else allowed_columns
            lines.append(
                "\n".join(
                    _render_table(
                        table_name,
                        allowed_columns,
                        self.table_specs.get(table_name),
                    )
                )
            )
        return "\n".join(lines)


@lru_cache
def load_catalog(workspace: str = "kalaam") -> SchemaCatalog:
    spec = load_workspace_file(workspace)
    allowlist = _load_allowlist(workspace)
    table_contexts = _render_table_contexts(spec, allowlist)
    return SchemaCatalog(
        workspace=workspace,
        dialect=spec.datasource.dialect,
        default_schema=spec.datasource.default_schema,
        connection_env_var=spec.datasource.connection_env_var,
        prompt_catalog=_render_prompt_catalog(spec, allowlist, table_contexts),
        table_specs=spec.tables,
        table_contexts=table_contexts,
        allowlist=allowlist,
    )


def _load_allowlist(
    workspace: str,
    workspaces_dir: Path = WORKSPACES_DIR,
) -> ColumnAllowlist:
    path = allowlist_path(workspace, workspaces_dir)
    if not path.is_file():
        raise SchemaContextError(f"allowlist snapshot not found: {path}")
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SchemaContextError(f"{path} must contain a JSON object.")
    document = cast(Mapping[str, object], raw)
    tables_raw = document.get("tables")
    if not isinstance(tables_raw, dict):
        raise SchemaContextError(f"{path} must contain a tables object.")

    allowlist: ColumnAllowlist = {}
    for table_name, columns_raw in cast(Mapping[str, object], tables_raw).items():
        if not isinstance(table_name, str) or not isinstance(columns_raw, list):
            raise SchemaContextError(f"{path} has an invalid table entry.")
        columns: set[str] = set()
        for column_name in columns_raw:
            if not isinstance(column_name, str):
                raise SchemaContextError(f"{path} has a non-string column name.")
            columns.add(column_name.lower())
        if not columns:
            raise SchemaContextError(f"{path} has an empty column set for {table_name}.")
        allowlist[table_name.lower()] = frozenset(columns)

    if not allowlist:
        raise SchemaContextError(f"{path} contains no allowed tables.")
    return allowlist


def _render_table_contexts(
    spec: WorkspaceFile,
    allowlist: ColumnAllowlist,
) -> dict[str, str]:
    contexts: dict[str, str] = {}
    for table_name in sorted(allowlist):
        table_spec = spec.tables.get(table_name)
        contexts[table_name] = "\n".join(
            _render_table(table_name, allowlist[table_name], table_spec)
        )
    return contexts


def _render_prompt_catalog(
    spec: WorkspaceFile,
    allowlist: ColumnAllowlist,
    table_contexts: Mapping[str, str],
) -> str:
    sections: list[str] = [
        f"Workspace: {spec.workspace}",
        f"Dialect: {spec.datasource.dialect}",
        f"Default schema: {spec.datasource.default_schema}",
    ]
    if spec.instructions:
        sections.extend(["Instructions:", spec.instructions.strip()])
    sections.append("Tables:")

    for table_name in sorted(allowlist):
        sections.append(table_contexts[table_name])

    if spec.glossary:
        sections.append("Glossary:")
        for entry in spec.glossary:
            mapped = f" maps_to={entry.maps_to}" if entry.maps_to else ""
            sections.append(f"- {entry.term}: {entry.definition}{mapped}")

    if spec.examples:
        sections.append("Verified examples:")
        for example in spec.examples:
            if not example.is_verified:
                continue
            tables = ", ".join(example.tables_used or [])
            sections.append(f"- Q: {example.question}")
            sections.append(f"  SQL: {example.sql_text}")
            if tables:
                sections.append(f"  Tables: {tables}")
    return "\n".join(sections)


def _render_table(
    table_name: str,
    allowed_columns: frozenset[str],
    table_spec: TableSpec | None,
) -> list[str]:
    lines = [f"- {table_name}"]
    if table_spec and table_spec.description:
        lines.append(f"  Description: {table_spec.description}")
    if table_spec and table_spec.instructions:
        lines.append(f"  Instructions: {table_spec.instructions.strip()}")
    lines.append(f"  Available columns: {', '.join(sorted(allowed_columns))}")
    if table_spec and table_spec.columns:
        enriched = [
            (column_name, column_spec)
            for column_name, column_spec in sorted(table_spec.columns.items())
            if column_name in allowed_columns
        ]
        if enriched:
            lines.append("  Enriched columns:")
            for column_name, column_spec in enriched:
                lines.extend(_render_column(column_name, column_spec))
    if table_spec and table_spec.join_hints:
        lines.append("  Join hints:")
        for hint in table_spec.join_hints:
            lines.append(f"  - {hint}")
    return lines


def _render_column(column_name: str, column_spec: ColumnSpec) -> list[str]:
    details: list[str] = []
    if column_spec.description:
        details.append(column_spec.description)
    if column_spec.values:
        sample = ", ".join(str(value) for value in column_spec.values[:8])
        details.append(f"values: {sample}")
    if column_spec.sensitive:
        details.append("sensitive")
    suffix = f" - {'; '.join(details)}" if details else ""
    return [f"  - {column_name}{suffix}"]
