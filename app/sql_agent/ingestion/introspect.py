"""Structural introspection of a workspace's target DB — no persistence.

Produces in-memory dataclasses for tables (with row-count estimates), columns
(with PK/FK flags), and FK relationships. Phase 2's loader/diff persists this;
here we only read. All access goes through ``target_db`` (read-only role +
``default_transaction_read_only=on`` + statement timeout).

Dry run (summary only, never row data):

    python -m app.sql_agent.ingestion.introspect --workspace kalaam
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import TextClause, bindparam, text

from app.sql_agent.target_db import get_target_engine

_SYSTEM_SCHEMAS = ("pg_catalog", "information_schema")


def _query(sql: str) -> TextClause:
    return text(sql).bindparams(bindparam("system_schemas", expanding=True))


@dataclass(frozen=True)
class IntrospectedColumn:
    column_name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    is_foreign_key: bool
    ordinal_position: int


@dataclass(frozen=True)
class IntrospectedTable:
    schema_name: str
    table_name: str
    row_count_estimate: int
    columns: tuple[IntrospectedColumn, ...]

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.table_name}"


@dataclass(frozen=True)
class IntrospectedForeignKey:
    constraint_name: str
    from_schema: str
    from_table: str
    from_column: str
    to_schema: str
    to_table: str
    to_column: str


@dataclass(frozen=True)
class IntrospectionResult:
    tables: tuple[IntrospectedTable, ...]
    foreign_keys: tuple[IntrospectedForeignKey, ...]

    @property
    def column_count(self) -> int:
        return sum(len(t.columns) for t in self.tables)


# Ordinary + partitioned parent tables, excluding partition children and all
# system schemas. Row estimates come from pg_class.reltuples (information_schema
# has no estimate); -1 means "never analyzed", clamped to 0.
_TABLES_SQL = _query(
    """
    SELECT n.nspname AS schema_name,
           c.relname AS table_name,
           GREATEST(c.reltuples, 0)::bigint AS row_count_estimate
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r', 'p')
      AND NOT c.relispartition
      AND n.nspname NOT IN :system_schemas
      AND n.nspname NOT LIKE 'pg\\_%'
    ORDER BY n.nspname, c.relname
    """
)

_COLUMNS_SQL = _query(
    """
    SELECT table_schema, table_name, column_name, data_type,
           is_nullable, ordinal_position
    FROM information_schema.columns
    WHERE table_schema NOT IN :system_schemas
      AND table_schema NOT LIKE 'pg\\_%'
    ORDER BY table_schema, table_name, ordinal_position
    """
)

_PK_SQL = _query(
    """
    SELECT n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name
    FROM pg_catalog.pg_constraint con
    JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    JOIN LATERAL unnest(con.conkey) AS k(attnum) ON TRUE
    JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
    WHERE con.contype = 'p'
      AND n.nspname NOT IN :system_schemas
      AND n.nspname NOT LIKE 'pg\\_%'
    """
)

# pg_constraint rather than information_schema: key_column_usage /
# constraint_column_usage cannot pair source->target columns positionally for
# multi-column FKs; unnest(conkey, confkey) keeps the pairing exact.
_FK_SQL = _query(
    """
    SELECT con.conname AS constraint_name,
           sn.nspname AS from_schema, sc.relname AS from_table, sa.attname AS from_column,
           tn.nspname AS to_schema, tc.relname AS to_table, ta.attname AS to_column
    FROM pg_catalog.pg_constraint con
    JOIN pg_catalog.pg_class sc ON sc.oid = con.conrelid
    JOIN pg_catalog.pg_namespace sn ON sn.oid = sc.relnamespace
    JOIN pg_catalog.pg_class tc ON tc.oid = con.confrelid
    JOIN pg_catalog.pg_namespace tn ON tn.oid = tc.relnamespace
    JOIN LATERAL unnest(con.conkey, con.confkey)
         WITH ORDINALITY AS pair(from_attnum, to_attnum, ord) ON TRUE
    JOIN pg_catalog.pg_attribute sa ON sa.attrelid = sc.oid AND sa.attnum = pair.from_attnum
    JOIN pg_catalog.pg_attribute ta ON ta.attrelid = tc.oid AND ta.attnum = pair.to_attnum
    WHERE con.contype = 'f'
      AND sn.nspname NOT IN :system_schemas
      AND sn.nspname NOT LIKE 'pg\\_%'
    ORDER BY sn.nspname, sc.relname, con.conname, pair.ord
    """
)


async def introspect_target(connection_env_var: str) -> IntrospectionResult:
    """Introspect all non-system tables/columns/FKs of the target DB."""
    engine = get_target_engine(connection_env_var)
    params = {"system_schemas": list(_SYSTEM_SCHEMAS)}
    async with engine.connect() as conn:
        table_rows = (await conn.execute(_TABLES_SQL, params)).all()
        column_rows = (await conn.execute(_COLUMNS_SQL, params)).all()
        pk_rows = (await conn.execute(_PK_SQL, params)).all()
        fk_rows = (await conn.execute(_FK_SQL, params)).all()

    pk_columns = {
        (str(r.schema_name), str(r.table_name), str(r.column_name)) for r in pk_rows
    }
    fk_columns = {
        (str(r.from_schema), str(r.from_table), str(r.from_column)) for r in fk_rows
    }
    table_keys = {(str(r.schema_name), str(r.table_name)) for r in table_rows}

    columns_by_table: dict[tuple[str, str], list[IntrospectedColumn]] = {}
    for r in column_rows:
        key = (str(r.table_schema), str(r.table_name))
        if key not in table_keys:  # views etc. — not tables we track
            continue
        columns_by_table.setdefault(key, []).append(
            IntrospectedColumn(
                column_name=str(r.column_name),
                data_type=str(r.data_type),
                is_nullable=str(r.is_nullable) == "YES",
                is_primary_key=(*key, str(r.column_name)) in pk_columns,
                is_foreign_key=(*key, str(r.column_name)) in fk_columns,
                ordinal_position=int(r.ordinal_position),
            )
        )

    tables = tuple(
        IntrospectedTable(
            schema_name=str(r.schema_name),
            table_name=str(r.table_name),
            row_count_estimate=int(r.row_count_estimate),
            columns=tuple(
                columns_by_table.get((str(r.schema_name), str(r.table_name)), ())
            ),
        )
        for r in table_rows
    )
    foreign_keys = tuple(
        IntrospectedForeignKey(
            constraint_name=str(r.constraint_name),
            from_schema=str(r.from_schema),
            from_table=str(r.from_table),
            from_column=str(r.from_column),
            to_schema=str(r.to_schema),
            to_table=str(r.to_table),
            to_column=str(r.to_column),
        )
        for r in fk_rows
    )
    return IntrospectionResult(tables=tables, foreign_keys=foreign_keys)


def workspace_env_var(workspace: str) -> str:
    """Env-var name convention for a workspace's read-only target-DB URL."""
    return f"{workspace.upper().replace('-', '_')}_READONLY_DATABASE_URL"


def _print_summary(workspace: str, env_var: str, result: IntrospectionResult) -> None:
    schema_counts: dict[str, int] = {}
    for t in result.tables:
        schema_counts[t.schema_name] = schema_counts.get(t.schema_name, 0) + 1
    pk_count = sum(1 for t in result.tables for c in t.columns if c.is_primary_key)
    schemas = ", ".join(f"{s} ({n})" for s, n in sorted(schema_counts.items())) or "-"
    first_tables = ", ".join(t.qualified_name for t in result.tables[:5]) or "-"
    print(f"SUMMARY workspace={workspace} env_var={env_var}")
    print(f"  tables:          {len(result.tables)}")
    print(f"  columns:         {result.column_count}")
    print(f"  pk columns:      {pk_count}")
    print(f"  fk links:        {len(result.foreign_keys)}")
    print(f"  schemas:         {schemas}")
    print(f"  first 5 tables:  {first_tables}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run introspection of a workspace's target DB (summary only)."
    )
    parser.add_argument(
        "--workspace", required=True, help="Workspace slug, e.g. kalaam"
    )
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    env_var = workspace_env_var(args.workspace)
    result = asyncio.run(introspect_target(env_var))
    _print_summary(args.workspace, env_var, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
