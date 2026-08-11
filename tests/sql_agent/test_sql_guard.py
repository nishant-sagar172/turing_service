from __future__ import annotations

import pytest

from app.sql_agent.schema_context import load_catalog
from app.sql_agent.validation import GuardError, GuardErrorCode, guard_sql


@pytest.fixture(scope="module")
def kalaam_allowlist() -> dict[str, frozenset[str]]:
    return load_catalog("kalaam").allowlist


def test_valid_select_gets_default_limit(
    kalaam_allowlist: dict[str, frozenset[str]],
) -> None:
    result = guard_sql(
        "SELECT id FROM patients",
        kalaam_allowlist,
        default_row_limit=200,
    )

    assert result.sql == "SELECT id FROM patients LIMIT 200"
    assert result.tables_used == ("patients",)
    assert result.columns_used == ("patients.id",)


def test_existing_limit_is_capped(
    kalaam_allowlist: dict[str, frozenset[str]],
) -> None:
    result = guard_sql(
        "SELECT id FROM patients LIMIT 5000",
        kalaam_allowlist,
        default_row_limit=200,
    )

    assert result.sql == "SELECT id FROM patients LIMIT 200"


def test_rejects_multi_statement(
    kalaam_allowlist: dict[str, frozenset[str]],
) -> None:
    with pytest.raises(GuardError) as exc:
        guard_sql(
            "SELECT id FROM patients; SELECT id FROM appointments",
            kalaam_allowlist,
            default_row_limit=200,
        )

    assert exc.value.code == GuardErrorCode.MULTI_STATEMENT


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM patients",
        "UPDATE patients SET name = 'x'",
        "INSERT INTO patients (id) VALUES (1)",
        "DROP TABLE patients",
    ],
)
def test_rejects_write_operations(
    sql: str,
    kalaam_allowlist: dict[str, frozenset[str]],
) -> None:
    with pytest.raises(GuardError) as exc:
        guard_sql(sql, kalaam_allowlist, default_row_limit=200)

    assert exc.value.code in {
        GuardErrorCode.NON_SELECT,
        GuardErrorCode.WRITE_OPERATION,
    }


def test_rejects_dangerous_function(
    kalaam_allowlist: dict[str, frozenset[str]],
) -> None:
    with pytest.raises(GuardError) as exc:
        guard_sql(
            "SELECT pg_read_file('/etc/passwd')",
            kalaam_allowlist,
            default_row_limit=200,
        )

    assert exc.value.code == GuardErrorCode.DANGEROUS_FUNCTION


def test_rejects_unknown_table(
    kalaam_allowlist: dict[str, frozenset[str]],
) -> None:
    with pytest.raises(GuardError) as exc:
        guard_sql(
            "SELECT id FROM hallucinated_table",
            kalaam_allowlist,
            default_row_limit=200,
        )

    assert exc.value.code == GuardErrorCode.UNKNOWN_TABLE


def test_rejects_unknown_column(
    kalaam_allowlist: dict[str, frozenset[str]],
) -> None:
    with pytest.raises(GuardError) as exc:
        guard_sql(
            "SELECT made_up_column FROM patients",
            kalaam_allowlist,
            default_row_limit=200,
        )

    assert exc.value.code == GuardErrorCode.UNKNOWN_COLUMN


def test_rejects_ambiguous_unqualified_column(
    kalaam_allowlist: dict[str, frozenset[str]],
) -> None:
    with pytest.raises(GuardError) as exc:
        guard_sql(
            "SELECT id FROM patients JOIN appointments ON appointments.patient_id = patients.id",
            kalaam_allowlist,
            default_row_limit=200,
        )

    assert exc.value.code == GuardErrorCode.AMBIGUOUS_COLUMN


def test_allows_qualified_join_columns(
    kalaam_allowlist: dict[str, frozenset[str]],
) -> None:
    result = guard_sql(
        "SELECT p.id FROM patients p JOIN appointments a ON a.patient_id = p.id",
        kalaam_allowlist,
        default_row_limit=200,
    )

    assert result.tables_used == ("appointments", "patients")
    assert "appointments.patient_id" in result.columns_used
    assert "patients.id" in result.columns_used


def test_rejects_non_literal_limit(
    kalaam_allowlist: dict[str, frozenset[str]],
) -> None:
    with pytest.raises(GuardError) as exc:
        guard_sql(
            "SELECT id FROM patients LIMIT patient_id",
            kalaam_allowlist,
            default_row_limit=200,
        )

    assert exc.value.code == GuardErrorCode.INVALID_LIMIT
