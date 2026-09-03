"""Full ingestion run: introspection + YAML enrichment -> control DB (plan §3).

    python -m app.sql_agent.ingestion.run --workspace kalaam

Merge policy: introspection is authoritative for *structure* (tables, columns,
types, PK/FK flags, FK relationships); the workspace YAML is authoritative for
*meaning* (descriptions, sensitive flags, observed values, manual join edges,
glossary, examples). Tables missing from a fresh introspection are soft-deleted
(``is_active=false``), never hard-deleted, so historical audit rows stay valid.

Change detection is content-hash based (``diff.py``): unchanged rows are not
touched; changed rows are updated and their ``embedding`` is cleared to NULL.
This run performs NO embedding calls — a later embed step simply processes
rows ``WHERE embedding IS NULL``, which this module guarantees is exactly the
set of new-or-changed rows.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.sql_agent.config import get_sql_agent_settings
from app.sql_agent.control_db.models import (
    ColumnMeta,
    Datasource,
    Example,
    GlossaryTerm,
    Relationship,
    TableMeta,
    Workspace,
)
from app.sql_agent.control_db.session import get_control_session_factory
from app.sql_agent.ingestion import diff
from app.sql_agent.ingestion.introspect import IntrospectionResult, introspect_target
from app.sql_agent.ingestion.loader import (
    ManualJoin,
    WorkspaceFile,
    extract_manual_relationships,
    load_workspace_file,
    validate_against_introspection,
)

TableKey = tuple[str, str]  # (schema_name, table_name)
RelationshipKey = tuple[uuid.UUID, str, uuid.UUID, str]


@dataclass
class EntityCounts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.created or self.updated or self.removed)

    def add(self, other: EntityCounts) -> None:
        self.created += other.created
        self.updated += other.updated
        self.unchanged += other.unchanged
        self.removed += other.removed

    @classmethod
    def from_diff(cls, result: diff.DiffResult[Any]) -> EntityCounts:
        return cls(
            created=len(result.created),
            updated=len(result.updated),
            unchanged=len(result.unchanged),
            removed=len(result.removed),
        )


@dataclass
class IngestReport:
    workspace: str
    tables: EntityCounts = field(default_factory=EntityCounts)
    columns: EntityCounts = field(default_factory=EntityCounts)
    relationships: EntityCounts = field(default_factory=EntityCounts)
    glossary: EntityCounts = field(default_factory=EntityCounts)
    examples: EntityCounts = field(default_factory=EntityCounts)
    warnings: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return any(
            counts.changed
            for counts in (
                self.tables,
                self.columns,
                self.relationships,
                self.glossary,
                self.examples,
            )
        )


@dataclass(frozen=True)
class DesiredColumn:
    column_name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    is_foreign_key: bool
    description: str | None
    is_sensitive: bool
    sample_values: list[Any] | None
    content_hash: str


@dataclass(frozen=True)
class DesiredTable:
    schema_name: str
    table_name: str
    description: str | None
    row_count_estimate: int
    columns: tuple[DesiredColumn, ...]
    content_hash: str


def build_desired_tables(
    spec: WorkspaceFile, introspection: IntrospectionResult
) -> dict[TableKey, DesiredTable]:
    """Merge introspected structure with YAML enrichment into the desired state."""
    default_schema = spec.datasource.default_schema
    desired: dict[TableKey, DesiredTable] = {}
    for table in introspection.tables:
        enrichment = (
            spec.tables.get(table.table_name)
            if table.schema_name == default_schema
            else None
        )
        columns: list[DesiredColumn] = []
        for column in table.columns:
            column_spec = (
                enrichment.columns.get(column.column_name) if enrichment else None
            )
            description = column_spec.description if column_spec else None
            is_sensitive = column_spec.sensitive if column_spec else False
            sample_values = column_spec.values if column_spec else None
            columns.append(
                DesiredColumn(
                    column_name=column.column_name,
                    data_type=column.data_type,
                    is_nullable=column.is_nullable,
                    is_primary_key=column.is_primary_key,
                    is_foreign_key=column.is_foreign_key,
                    description=description,
                    is_sensitive=is_sensitive,
                    sample_values=sample_values,
                    content_hash=diff.column_content_hash(
                        column_name=column.column_name,
                        data_type=column.data_type,
                        is_nullable=column.is_nullable,
                        is_primary_key=column.is_primary_key,
                        is_foreign_key=column.is_foreign_key,
                        description=description,
                        is_sensitive=is_sensitive,
                        sample_values=sample_values,
                    ),
                )
            )
        table_description = enrichment.description if enrichment else None
        desired[(table.schema_name, table.table_name)] = DesiredTable(
            schema_name=table.schema_name,
            table_name=table.table_name,
            description=table_description,
            row_count_estimate=table.row_count_estimate,
            columns=tuple(columns),
            content_hash=diff.table_content_hash(
                schema_name=table.schema_name,
                table_name=table.table_name,
                description=table_description,
                column_hashes=[c.content_hash for c in columns],
            ),
        )
    return desired


async def _upsert_workspace(session: AsyncSession, spec: WorkspaceFile) -> Workspace:
    workspace = await session.scalar(
        select(Workspace).where(Workspace.slug == spec.workspace)
    )
    if workspace is None:
        workspace = Workspace(name=spec.workspace, slug=spec.workspace, status="active")
        session.add(workspace)
        await session.flush()
    return workspace


async def _upsert_datasource(
    session: AsyncSession, workspace: Workspace, spec: WorkspaceFile
) -> None:
    settings = get_sql_agent_settings()
    env_var = spec.datasource.connection_env_var
    raw_url = os.environ.get(env_var, "")
    role_name = make_url(raw_url).username if raw_url else None

    datasource = await session.scalar(
        select(Datasource).where(Datasource.workspace_id == workspace.id)
    )
    if datasource is None:
        datasource = Datasource(workspace_id=workspace.id)
        session.add(datasource)
    datasource.dialect = spec.datasource.dialect
    datasource.connection_env_var = env_var
    datasource.read_only_role_name = role_name
    datasource.statement_timeout_ms = settings.sql_agent_statement_timeout_ms
    datasource.default_row_limit = settings.sql_agent_default_row_limit
    await session.flush()


async def _sync_tables(
    session: AsyncSession,
    workspace: Workspace,
    desired: dict[TableKey, DesiredTable],
) -> tuple[EntityCounts, dict[TableKey, TableMeta]]:
    rows = (
        await session.scalars(
            select(TableMeta).where(TableMeta.workspace_id == workspace.id)
        )
    ).all()
    existing: dict[TableKey, TableMeta] = {
        (row.schema_name, row.table_name): row for row in rows
    }
    states = {
        key: diff.RowState(content_hash=row.source_hash, is_active=row.is_active)
        for key, row in existing.items()
    }
    result = diff.diff_rows(states, {key: d.content_hash for key, d in desired.items()})

    live: dict[TableKey, TableMeta] = {}
    for key in result.created:
        d = desired[key]
        row = TableMeta(
            workspace_id=workspace.id,
            schema_name=d.schema_name,
            table_name=d.table_name,
            description=d.description,
            is_reviewed=False,
            row_count_estimate=d.row_count_estimate,
            is_active=True,
            source_hash=d.content_hash,
        )
        session.add(row)
        live[key] = row
    for key in result.updated:
        d = desired[key]
        row = existing[key]
        row.description = d.description
        row.row_count_estimate = d.row_count_estimate
        row.is_active = True
        row.source_hash = d.content_hash
        row.embedding = None
        # Content changed, so any prior human review no longer applies.
        row.is_reviewed = False
        live[key] = row
    for key in result.unchanged:
        if key not in desired:
            continue  # already soft-deleted and still absent — leave untouched
        row = existing[key]
        # Row-count drift is metadata refresh, not a content change: no hash
        # churn, no re-embedding, not counted as "updated".
        if row.row_count_estimate != desired[key].row_count_estimate:
            row.row_count_estimate = desired[key].row_count_estimate
        live[key] = row
    for key in result.removed:
        existing[key].is_active = False

    await session.flush()
    return EntityCounts.from_diff(result), live


async def _sync_columns(
    session: AsyncSession,
    desired: dict[TableKey, DesiredTable],
    live_tables: dict[TableKey, TableMeta],
) -> EntityCounts:
    table_ids = [table.id for table in live_tables.values()]
    rows = (
        await session.scalars(
            select(ColumnMeta).where(ColumnMeta.table_id.in_(table_ids))
        )
    ).all()
    rows_by_table: dict[uuid.UUID, dict[str, ColumnMeta]] = {}
    for row in rows:
        rows_by_table.setdefault(row.table_id, {})[row.column_name] = row

    totals = EntityCounts()
    for key, desired_table in desired.items():
        table = live_tables[key]
        existing = rows_by_table.get(table.id, {})
        states = {
            name: diff.RowState(
                content_hash=diff.column_content_hash(
                    column_name=row.column_name,
                    data_type=row.data_type,
                    is_nullable=row.is_nullable,
                    is_primary_key=row.is_primary_key,
                    is_foreign_key=row.is_foreign_key,
                    description=row.description,
                    is_sensitive=row.is_sensitive,
                    sample_values=row.sample_values,
                )
            )
            for name, row in existing.items()
        }
        fresh = {c.column_name: c for c in desired_table.columns}
        result = diff.diff_rows(states, {n: c.content_hash for n, c in fresh.items()})

        for name in result.created:
            c = fresh[name]
            session.add(
                ColumnMeta(
                    table_id=table.id,
                    column_name=c.column_name,
                    data_type=c.data_type,
                    is_nullable=c.is_nullable,
                    is_primary_key=c.is_primary_key,
                    is_foreign_key=c.is_foreign_key,
                    description=c.description,
                    is_reviewed=False,
                    sample_values=c.sample_values,
                    is_sensitive=c.is_sensitive,
                )
            )
        for name in result.updated:
            c = fresh[name]
            row = existing[name]
            row.data_type = c.data_type
            row.is_nullable = c.is_nullable
            row.is_primary_key = c.is_primary_key
            row.is_foreign_key = c.is_foreign_key
            row.description = c.description
            row.sample_values = c.sample_values
            row.is_sensitive = c.is_sensitive
            row.is_reviewed = False
        for name in result.removed:
            # Columns have no is_active flag: a stale row would let the SQL
            # validator approve references to a column the DB no longer has,
            # so vanished columns are hard-deleted (fail closed).
            await session.delete(existing[name])

        totals.add(EntityCounts.from_diff(result))

    await session.flush()
    return totals


async def _sync_relationships(
    session: AsyncSession,
    workspace: Workspace,
    spec: WorkspaceFile,
    introspection: IntrospectionResult,
    manual_joins: list[ManualJoin],
    live_tables: dict[TableKey, TableMeta],
) -> EntityCounts:
    default_schema = spec.datasource.default_schema
    desired: dict[RelationshipKey, tuple[str, str | None]] = {}

    for fk in introspection.foreign_keys:
        from_table = live_tables.get((fk.from_schema, fk.from_table))
        to_table = live_tables.get((fk.to_schema, fk.to_table))
        if from_table is None or to_table is None:
            continue
        key = (from_table.id, fk.from_column, to_table.id, fk.to_column)
        desired[key] = ("fk_auto", None)

    for join in manual_joins:
        from_table = live_tables.get((default_schema, join.from_table))
        to_table = live_tables.get((default_schema, join.to_table))
        if from_table is None or to_table is None:
            continue
        key = (from_table.id, join.from_column, to_table.id, join.to_column)
        # A real FK constraint outranks a prose hint for the same edge.
        if key not in desired:
            desired[key] = ("manual", join.join_hint)

    rows = (
        await session.scalars(
            select(Relationship).where(Relationship.workspace_id == workspace.id)
        )
    ).all()
    existing: dict[RelationshipKey, Relationship] = {}
    duplicates: list[Relationship] = []
    for row in rows:
        key = (row.from_table_id, row.from_column, row.to_table_id, row.to_column)
        if key in existing:
            duplicates.append(row)
        else:
            existing[key] = row

    counts = EntityCounts()
    for row in duplicates:
        await session.delete(row)
        counts.removed += 1

    for key, (rel_type, hint) in desired.items():
        row_existing = existing.get(key)
        if row_existing is None:
            session.add(
                Relationship(
                    workspace_id=workspace.id,
                    from_table_id=key[0],
                    from_column=key[1],
                    to_table_id=key[2],
                    to_column=key[3],
                    relationship_type=rel_type,
                    join_hint=hint,
                )
            )
            counts.created += 1
        elif (row_existing.relationship_type, row_existing.join_hint) != (
            rel_type,
            hint,
        ):
            row_existing.relationship_type = rel_type
            row_existing.join_hint = hint
            counts.updated += 1
        else:
            counts.unchanged += 1

    for key, row in existing.items():
        if key not in desired:
            await session.delete(row)
            counts.removed += 1

    await session.flush()
    return counts


async def _sync_glossary(
    session: AsyncSession,
    workspace: Workspace,
    spec: WorkspaceFile,
    live_tables: dict[TableKey, TableMeta],
) -> EntityCounts:
    default_schema = spec.datasource.default_schema
    table_by_name = {
        key[1]: table for key, table in live_tables.items() if key[0] == default_schema
    }
    table_name_by_id = {table.id: name for name, table in table_by_name.items()}

    fresh_specs = {entry.term: entry for entry in spec.glossary}
    fresh_hashes = {
        term: diff.glossary_content_hash(
            term=term,
            definition=entry.definition,
            maps_to_table=entry.maps_to if entry.maps_to in table_by_name else None,
            maps_to_column=None,
        )
        for term, entry in fresh_specs.items()
    }

    rows = (
        await session.scalars(
            select(GlossaryTerm).where(GlossaryTerm.workspace_id == workspace.id)
        )
    ).all()
    existing = {row.term: row for row in rows}
    states = {
        term: diff.RowState(
            content_hash=diff.glossary_content_hash(
                term=term,
                definition=row.definition,
                maps_to_table=table_name_by_id.get(row.maps_to_table_id)
                if row.maps_to_table_id
                else None,
                maps_to_column=None,
            )
        )
        for term, row in existing.items()
    }
    result = diff.diff_rows(states, fresh_hashes)

    for term in result.created:
        entry = fresh_specs[term]
        mapped = table_by_name.get(entry.maps_to) if entry.maps_to else None
        session.add(
            GlossaryTerm(
                workspace_id=workspace.id,
                term=term,
                definition=entry.definition,
                maps_to_table_id=mapped.id if mapped else None,
            )
        )
    for term in result.updated:
        entry = fresh_specs[term]
        mapped = table_by_name.get(entry.maps_to) if entry.maps_to else None
        row = existing[term]
        row.definition = entry.definition
        row.maps_to_table_id = mapped.id if mapped else None
        row.embedding = None
    for term in result.removed:
        # Glossary rows only ever come from the YAML (source of truth); a
        # stale definition would actively mislead retrieval, so delete.
        await session.delete(existing[term])

    await session.flush()
    return EntityCounts.from_diff(result)


async def _sync_examples(
    session: AsyncSession, workspace: Workspace, spec: WorkspaceFile
) -> EntityCounts:
    """Upsert-only: examples also enter this table from verified live runs
    (plan §5), and those must never be deleted just because they aren't in
    the YAML. Counts cover YAML-sourced examples only.
    """
    rows = (
        await session.scalars(
            select(Example).where(Example.workspace_id == workspace.id)
        )
    ).all()
    existing = {row.question: row for row in rows}

    counts = EntityCounts()
    for example in spec.examples:
        fresh_hash = diff.example_content_hash(
            question=example.question,
            sql_text=example.sql_text,
            tables_used=example.tables_used,
            is_verified=example.is_verified,
        )
        row = existing.get(example.question)
        if row is None:
            session.add(
                Example(
                    workspace_id=workspace.id,
                    question=example.question,
                    sql_text=example.sql_text,
                    tables_used=example.tables_used,
                    is_verified=example.is_verified,
                )
            )
            counts.created += 1
            continue
        existing_hash = diff.example_content_hash(
            question=row.question,
            sql_text=row.sql_text,
            tables_used=row.tables_used,
            is_verified=row.is_verified,
        )
        if existing_hash == fresh_hash:
            counts.unchanged += 1
        else:
            row.sql_text = example.sql_text
            row.tables_used = example.tables_used
            row.is_verified = example.is_verified
            row.embedding = None
            counts.updated += 1

    await session.flush()
    return counts


async def ingest_workspace(slug: str) -> IngestReport:
    """Run one full ingestion for a workspace; returns the change report.

    Everything lands in a single control-DB transaction: either the whole
    merged snapshot commits or nothing does. Embedding is a separate later
    step (rows needing it are exactly those with embedding IS NULL).
    """
    spec = load_workspace_file(slug)
    introspection = await introspect_target(spec.datasource.connection_env_var)

    report = IngestReport(workspace=slug)
    report.warnings.extend(validate_against_introspection(spec, introspection))
    manual_joins, join_warnings = extract_manual_relationships(spec, introspection)
    report.warnings.extend(join_warnings)

    desired = build_desired_tables(spec, introspection)

    factory = get_control_session_factory()
    async with factory() as session:
        async with session.begin():
            workspace = await _upsert_workspace(session, spec)
            await _upsert_datasource(session, workspace, spec)
            report.tables, live_tables = await _sync_tables(session, workspace, desired)
            report.columns = await _sync_columns(session, desired, live_tables)
            report.relationships = await _sync_relationships(
                session, workspace, spec, introspection, manual_joins, live_tables
            )
            report.glossary = await _sync_glossary(
                session, workspace, spec, live_tables
            )
            report.examples = await _sync_examples(session, workspace, spec)

    return report


def _print_report(report: IngestReport) -> None:
    def line(label: str, counts: EntityCounts, removal: str) -> str:
        return (
            f"  {label:<15} created={counts.created} updated={counts.updated} "
            f"unchanged={counts.unchanged} {removal}={counts.removed}"
        )

    print(
        f"INGEST workspace={report.workspace} changed={'yes' if report.changed else 'no'}"
    )
    print(line("tables:", report.tables, "deactivated"))
    print(line("columns:", report.columns, "deleted"))
    print(line("relationships:", report.relationships, "deleted"))
    print(line("glossary:", report.glossary, "deleted"))
    print(line("examples:", report.examples, "deleted"))
    if report.warnings:
        print(f"  warnings ({len(report.warnings)}):")
        for warning in report.warnings:
            print(f"    - {warning}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest a workspace's schema + YAML enrichment into the control DB."
    )
    parser.add_argument(
        "--workspace", required=True, help="Workspace slug, e.g. kalaam"
    )
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    report = asyncio.run(ingest_workspace(args.workspace))
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
