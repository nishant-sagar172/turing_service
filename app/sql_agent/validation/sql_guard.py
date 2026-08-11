"""Deterministic SQL safety validation for generated Kalaam queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from enum import Enum

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

ColumnAllowlist = dict[str, frozenset[str]]

_DANGEROUS_FUNCTIONS = frozenset(
    {
        "copy",
        "dblink",
        "dblink_connect",
        "dblink_exec",
        "lo_export",
        "lo_import",
        "pg_execute_server_program",
        "pg_ls_dir",
        "pg_read_binary_file",
        "pg_read_file",
        "pg_stat_file",
    }
)

_WRITE_EXPRESSIONS: tuple[type[exp.Expression], ...] = (
    exp.Alter,
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Insert,
    exp.Merge,
    exp.TruncateTable,
    exp.Update,
)


class GuardErrorCode(str, Enum):
    PARSE_ERROR = "parse_error"
    MULTI_STATEMENT = "multi_statement"
    NON_SELECT = "non_select"
    WRITE_OPERATION = "write_operation"
    DANGEROUS_FUNCTION = "dangerous_function"
    UNKNOWN_TABLE = "unknown_table"
    UNKNOWN_COLUMN = "unknown_column"
    AMBIGUOUS_COLUMN = "ambiguous_column"
    INVALID_LIMIT = "invalid_limit"


class GuardError(ValueError):
    """Static SQL guard failure with a machine-readable code."""

    def __init__(self, code: GuardErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class GuardResult:
    sql: str
    tables_used: tuple[str, ...]
    columns_used: tuple[str, ...]


def guard_sql(
    sql: str,
    allowlist: ColumnAllowlist,
    *,
    default_row_limit: int,
    default_schema: str = "public",
) -> GuardResult:
    """Validate and normalize a generated query.

    The function is intentionally stricter than Postgres. If a reference cannot
    be resolved deterministically from the allowlist, it is rejected and can be
    sent through the repair loop.
    """
    if default_row_limit <= 0:
        raise GuardError(
            GuardErrorCode.INVALID_LIMIT,
            "default_row_limit must be positive.",
        )
    expression = _parse_single_statement(sql)
    if not isinstance(expression, exp.Select):
        raise GuardError(
            GuardErrorCode.NON_SELECT,
            "Only a single top-level SELECT or WITH query is allowed.",
        )
    _reject_writes_and_dangerous_functions(expression)
    limited = _enforce_limit(expression, default_row_limit)

    reference_index = _build_reference_index(limited, allowlist, default_schema)
    columns_used = _validate_columns(limited, allowlist, reference_index, default_schema)
    return GuardResult(
        sql=limited.sql(dialect="postgres"),
        tables_used=tuple(sorted(reference_index.physical_tables)),
        columns_used=tuple(sorted(columns_used)),
    )


def _parse_single_statement(sql: str) -> exp.Expression:
    try:
        expressions = [item for item in sqlglot.parse(sql, read="postgres") if item is not None]
    except ParseError as exc:
        raise GuardError(GuardErrorCode.PARSE_ERROR, str(exc)) from exc
    if len(expressions) != 1:
        raise GuardError(
            GuardErrorCode.MULTI_STATEMENT,
            "Exactly one SQL statement is allowed.",
        )
    return cast(exp.Expression, expressions[0])


def _reject_writes_and_dangerous_functions(expression: exp.Expression) -> None:
    for expression_type in _WRITE_EXPRESSIONS:
        if expression.find(expression_type) is not None:
            raise GuardError(
                GuardErrorCode.WRITE_OPERATION,
                "Write operations are not allowed.",
            )
    for function in expression.find_all(exp.Func):
        name = function.sql_name().lower()
        if name in _DANGEROUS_FUNCTIONS or name.startswith("lo_"):
            raise GuardError(
                GuardErrorCode.DANGEROUS_FUNCTION,
                f"Function {name!r} is not allowed.",
            )
    for anonymous in expression.find_all(exp.Anonymous):
        name = anonymous.name.lower()
        if name in _DANGEROUS_FUNCTIONS or name.startswith("lo_"):
            raise GuardError(
                GuardErrorCode.DANGEROUS_FUNCTION,
                f"Function {name!r} is not allowed.",
            )


@dataclass(frozen=True)
class _ReferenceIndex:
    alias_to_table: dict[str, str]
    derived_columns: dict[str, frozenset[str]]
    output_aliases: frozenset[str]
    physical_tables: frozenset[str]


def _build_reference_index(
    expression: exp.Expression,
    allowlist: ColumnAllowlist,
    default_schema: str,
) -> _ReferenceIndex:
    cte_columns = _collect_cte_columns(expression)
    derived_columns = cte_columns | _collect_subquery_columns(expression)
    alias_to_table: dict[str, str] = {}
    physical_tables: set[str] = set()

    for table in expression.find_all(exp.Table):
        table_name = table.name.lower()
        if table_name in derived_columns:
            continue
        schema_name = table.db.lower() if table.db else default_schema
        if schema_name != default_schema:
            raise GuardError(
                GuardErrorCode.UNKNOWN_TABLE,
                f"Only schema {default_schema!r} is allowed; got {schema_name!r}.",
            )
        if table_name not in allowlist:
            raise GuardError(
                GuardErrorCode.UNKNOWN_TABLE,
                f"Unknown table {table_name!r}.",
            )
        physical_tables.add(table_name)
        alias = table.alias_or_name.lower()
        existing = alias_to_table.get(alias)
        if existing is not None and existing != table_name:
            raise GuardError(
                GuardErrorCode.UNKNOWN_TABLE,
                f"Alias {alias!r} refers to more than one table.",
            )
        alias_to_table[alias] = table_name
        alias_to_table.setdefault(table_name, table_name)

    return _ReferenceIndex(
        alias_to_table=alias_to_table,
        derived_columns=derived_columns,
        output_aliases=frozenset(_collect_output_aliases(expression)),
        physical_tables=frozenset(physical_tables),
    )


def _collect_cte_columns(expression: exp.Expression) -> dict[str, frozenset[str]]:
    result: dict[str, frozenset[str]] = {}
    for cte in expression.find_all(exp.CTE):
        alias = cte.alias_or_name.lower()
        if not alias:
            continue
        result[alias] = frozenset(_select_output_names(cte.this))
    return result


def _collect_subquery_columns(expression: exp.Expression) -> dict[str, frozenset[str]]:
    result: dict[str, frozenset[str]] = {}
    for subquery in expression.find_all(exp.Subquery):
        alias = subquery.alias_or_name.lower()
        if not alias:
            continue
        result[alias] = frozenset(_select_output_names(subquery.this))
    return result


def _collect_output_aliases(expression: exp.Expression) -> set[str]:
    aliases: set[str] = set()
    for select in expression.find_all(exp.Select):
        for selected in select.expressions:
            alias = selected.alias
            if alias:
                aliases.add(alias.lower())
    return aliases


def _select_output_names(expression: exp.Expression) -> set[str]:
    if not isinstance(expression, exp.Select):
        return set()
    names: set[str] = set()
    for selected in expression.expressions:
        alias = selected.alias_or_name
        if alias:
            names.add(alias.lower())
    return names


def _validate_columns(
    expression: exp.Expression,
    allowlist: ColumnAllowlist,
    index: _ReferenceIndex,
    default_schema: str,
) -> set[str]:
    columns_used: set[str] = set()
    for column in expression.find_all(exp.Column):
        if isinstance(column.this, exp.Star):
            continue
        column_name = column.name.lower()
        qualifier = column.table.lower() if column.table else ""
        schema_name = column.db.lower() if column.db else default_schema
        if schema_name != default_schema:
            raise GuardError(
                GuardErrorCode.UNKNOWN_COLUMN,
                f"Only schema {default_schema!r} is allowed in column references.",
            )

        if qualifier:
            physical_table = index.alias_to_table.get(qualifier)
            if physical_table is not None:
                _require_column(allowlist, physical_table, column_name)
                columns_used.add(f"{physical_table}.{column_name}")
                continue
            derived = index.derived_columns.get(qualifier)
            if derived is not None and (not derived or column_name in derived):
                continue
            raise GuardError(
                GuardErrorCode.UNKNOWN_COLUMN,
                f"Unknown table or alias {qualifier!r} for column {column_name!r}.",
            )

        if column_name in index.output_aliases:
            continue
        matches = [
            table_name
            for table_name in index.physical_tables
            if column_name in allowlist[table_name]
        ]
        if len(matches) == 1:
            columns_used.add(f"{matches[0]}.{column_name}")
            continue
        if not matches:
            if any(column_name in cols for cols in index.derived_columns.values()):
                continue
            raise GuardError(
                GuardErrorCode.UNKNOWN_COLUMN,
                f"Unknown unqualified column {column_name!r}.",
            )
        raise GuardError(
            GuardErrorCode.AMBIGUOUS_COLUMN,
            f"Ambiguous unqualified column {column_name!r}; qualify it with a table alias.",
        )
    return columns_used


def _require_column(
    allowlist: ColumnAllowlist,
    table_name: str,
    column_name: str,
) -> None:
    if column_name not in allowlist[table_name]:
        raise GuardError(
            GuardErrorCode.UNKNOWN_COLUMN,
            f"Unknown column {table_name}.{column_name}.",
        )


def _enforce_limit(expression: exp.Select, default_row_limit: int) -> exp.Select:
    limit = expression.args.get("limit")
    if limit is None:
        return expression.limit(default_row_limit, copy=True)
    if not isinstance(limit, exp.Limit):
        raise GuardError(GuardErrorCode.INVALID_LIMIT, "Invalid LIMIT clause.")
    limit_expression = limit.expression
    if not isinstance(limit_expression, exp.Literal) or not limit_expression.is_int:
        raise GuardError(
            GuardErrorCode.INVALID_LIMIT,
            "LIMIT must be a positive integer literal.",
        )
    value = int(limit_expression.this)
    if value <= 0:
        raise GuardError(
            GuardErrorCode.INVALID_LIMIT,
            "LIMIT must be a positive integer literal.",
        )
    if value <= default_row_limit:
        return expression.copy()
    return expression.limit(default_row_limit, copy=True)
