"""Loader for a workspace's hand-authored YAML enrichment (plan §3).

Parses and validates ``app/sql_agent/workspaces/<slug>.yaml`` into typed
pydantic models: workspace header, datasource, per-table descriptions/columns
(with observed values + sensitive flags) and join_hints, cross-cutting
instructions, glossary, and curated examples.

Validation stance:
- Structural problems in the file itself (unknown keys, missing required
  fields, a credential where an env-var *name* belongs) fail loudly —
  a malformed source-of-truth file must not half-ingest.
- Names that don't line up with live introspection (a YAML table/column the
  target DB no longer has, a glossary maps_to that isn't a known table) are
  collected as warnings, never a crash — the DB moved, the file lags, and
  ingestion must still land everything that does match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.sql_agent.ingestion.introspect import IntrospectionResult

WORKSPACES_DIR = Path(__file__).resolve().parents[1] / "workspaces"

_ENV_VAR_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]*")
_LEADING_IDENT_RE = re.compile(r"^[\"'`]?([A-Za-z_][A-Za-z0-9_]*)")
_TABLE_COLUMN_REF_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")


class WorkspaceFileError(ValueError):
    """The workspace YAML file is missing or structurally invalid."""


class ColumnSpec(BaseModel):
    """Enrichment for one column: description, observed values, PII flag."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    values: list[Any] | None = None
    sensitive: bool = False


class TableSpec(BaseModel):
    """Enrichment for one table: description, column specs, free-text join hints."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    instructions: str | None = None
    columns: dict[str, ColumnSpec] = Field(default_factory=dict)
    join_hints: list[str] = Field(default_factory=list)

    @field_validator("columns", mode="before")
    @classmethod
    def _coerce_bare_columns(cls, value: Any) -> Any:
        if value is None:
            return {}
        if isinstance(value, dict):
            return {key: ({} if spec is None else spec) for key, spec in value.items()}
        return value


class DatasourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dialect: str = "postgresql"
    default_schema: str = "public"
    connection_env_var: str

    @field_validator("connection_env_var")
    @classmethod
    def _must_be_env_var_name(cls, value: str) -> str:
        if not _ENV_VAR_NAME_RE.fullmatch(value):
            raise ValueError(
                "connection_env_var must be an environment-variable NAME "
                "(e.g. KALAAM_READONLY_DATABASE_URL) — never a connection "
                "string or credential"
            )
        return value


class GlossarySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str
    definition: str
    maps_to: str | None = None


class ExampleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    sql_text: str
    tables_used: list[str] | None = None
    is_verified: bool = False


class WorkspaceFile(BaseModel):
    """The full parsed <slug>.yaml enrichment file."""

    model_config = ConfigDict(extra="forbid")

    workspace: str
    version: int = 1
    datasource: DatasourceSpec
    instructions: str | None = None
    tables: dict[str, TableSpec] = Field(default_factory=dict)
    glossary: list[GlossarySpec] = Field(default_factory=list)
    examples: list[ExampleSpec] = Field(default_factory=list)

    @field_validator("tables", mode="before")
    @classmethod
    def _coerce_bare_tables(cls, value: Any) -> Any:
        if value is None:
            return {}
        if isinstance(value, dict):
            return {key: ({} if spec is None else spec) for key, spec in value.items()}
        return value

    @field_validator("glossary")
    @classmethod
    def _unique_terms(cls, value: list[GlossarySpec]) -> list[GlossarySpec]:
        seen: set[str] = set()
        for entry in value:
            if entry.term in seen:
                raise ValueError(f"duplicate glossary term: {entry.term!r}")
            seen.add(entry.term)
        return value


@dataclass(frozen=True)
class ManualJoin:
    """A join_hint resolved to a concrete (table, column) -> (table, column) pair."""

    from_table: str
    from_column: str
    to_table: str
    to_column: str
    join_hint: str


def workspace_file_path(slug: str, workspaces_dir: Path = WORKSPACES_DIR) -> Path:
    return workspaces_dir / f"{slug}.yaml"


def load_workspace_file(
    slug: str, workspaces_dir: Path = WORKSPACES_DIR
) -> WorkspaceFile:
    """Parse + validate the workspace YAML; raise WorkspaceFileError on any
    structural problem (this file is the source of truth — half-loading it
    would silently ingest a partial picture)."""
    path = workspace_file_path(slug, workspaces_dir)
    if not path.is_file():
        raise WorkspaceFileError(f"workspace file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise WorkspaceFileError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise WorkspaceFileError(f"{path} must contain a YAML mapping at top level")
    try:
        spec = WorkspaceFile.model_validate(raw)
    except ValidationError as exc:
        raise WorkspaceFileError(f"{path} failed validation:\n{exc}") from exc
    if spec.workspace != slug:
        raise WorkspaceFileError(
            f"{path} declares workspace {spec.workspace!r} but was loaded for "
            f"slug {slug!r} — refusing to ingest under the wrong workspace"
        )
    return spec


def _known_columns_by_table(
    spec: WorkspaceFile, introspection: IntrospectionResult
) -> dict[str, set[str]]:
    """Unqualified table -> column names, for the datasource's default schema."""
    default_schema = spec.datasource.default_schema
    return {
        table.table_name: {column.column_name for column in table.columns}
        for table in introspection.tables
        if table.schema_name == default_schema
    }


def validate_against_introspection(
    spec: WorkspaceFile, introspection: IntrospectionResult
) -> list[str]:
    """Cross-check YAML names against live introspection; return warnings.

    Nothing here raises: enrichment naming a table/column the DB no longer
    has must not block ingesting everything that still matches.
    """
    warnings: list[str] = []
    known = _known_columns_by_table(spec, introspection)
    if not known:
        warnings.append(
            f"introspection returned no tables in default schema "
            f"{spec.datasource.default_schema!r}"
        )

    for table_name, table_spec in spec.tables.items():
        columns = known.get(table_name)
        if columns is None:
            warnings.append(
                f"YAML table {table_name!r} not found in introspection "
                f"(schema {spec.datasource.default_schema!r}); its enrichment "
                "will be skipped"
            )
            continue
        for column_name in table_spec.columns:
            if column_name not in columns:
                warnings.append(
                    f"YAML column {table_name}.{column_name} not found in "
                    "introspection; its enrichment will be skipped"
                )

    for entry in spec.glossary:
        if entry.maps_to is not None and entry.maps_to not in known:
            warnings.append(
                f"glossary term {entry.term!r} maps_to {entry.maps_to!r}, which "
                "is not a single known table; maps_to_table_id will be NULL"
            )

    for example in spec.examples:
        for table_name in example.tables_used or []:
            if table_name not in known:
                warnings.append(
                    f"example {example.question!r} lists unknown table "
                    f"{table_name!r} in tables_used"
                )

    return warnings


def extract_manual_relationships(
    spec: WorkspaceFile, introspection: IntrospectionResult
) -> tuple[list[ManualJoin], list[str]]:
    """Resolve free-text join_hints into concrete manual relationships.

    A hint yields a relationship row only when it is unambiguously concrete:
    its leading identifier is a real column of the hinted table AND it
    references a real ``other_table.column`` elsewhere in the text. Anything
    fuzzier (polymorphic prose, external-system ids, table-only mentions) is
    skipped with a warning — a wrong join edge poisons retrieval, a missing
    one only weakens it.
    """
    joins: list[ManualJoin] = []
    warnings: list[str] = []
    known = _known_columns_by_table(spec, introspection)

    for table_name, table_spec in spec.tables.items():
        own_columns = known.get(table_name)
        if own_columns is None:
            continue  # already warned by validate_against_introspection
        for hint in table_spec.join_hints:
            leading = _LEADING_IDENT_RE.match(hint.strip())
            from_column = (
                leading.group(1)
                if leading and leading.group(1) in own_columns
                else None
            )
            target = next(
                (
                    (ref_table, ref_column)
                    for ref_table, ref_column in _TABLE_COLUMN_REF_RE.findall(hint)
                    if ref_table != table_name
                    and ref_table in known
                    and ref_column in known[ref_table]
                ),
                None,
            )
            if from_column is None or target is None:
                warnings.append(
                    f"join_hint on {table_name!r} does not name a concrete "
                    f"column pair; no relationship row created: {hint!r}"
                )
                continue
            joins.append(
                ManualJoin(
                    from_table=table_name,
                    from_column=from_column,
                    to_table=target[0],
                    to_column=target[1],
                    join_hint=hint,
                )
            )

    return joins, warnings
