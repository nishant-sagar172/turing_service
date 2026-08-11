"""Unit tests for ingestion change detection (app.sql_agent.ingestion.diff).

Pure in-memory fixtures — no DB, no LLM, no network.
"""

from __future__ import annotations

from typing import Any

from app.sql_agent.ingestion import diff


def _column_hash(**overrides: Any) -> str:
    base: dict[str, Any] = {
        "column_name": "uhid",
        "data_type": "character varying",
        "is_nullable": False,
        "is_primary_key": False,
        "is_foreign_key": False,
        "description": "Hospital-issued Unique Health ID.",
        "is_sensitive": True,
        "sample_values": None,
    }
    base.update(overrides)
    return diff.column_content_hash(**base)


class TestContentHashes:
    def test_column_hash_is_deterministic(self) -> None:
        assert _column_hash() == _column_hash()

    def test_column_hash_changes_per_content_field(self) -> None:
        base = _column_hash()
        assert _column_hash(description="Something else.") != base
        assert _column_hash(data_type="text") != base
        assert _column_hash(is_sensitive=False) != base
        assert _column_hash(is_nullable=True) != base
        assert _column_hash(is_primary_key=True) != base
        assert _column_hash(is_foreign_key=True) != base
        assert _column_hash(sample_values=["a", "b"]) != base

    def test_sample_values_order_matters(self) -> None:
        # Observed-values lists are content: reordering is a change.
        assert _column_hash(sample_values=["a", "b"]) != _column_hash(
            sample_values=["b", "a"]
        )

    def test_none_and_empty_description_differ(self) -> None:
        assert _column_hash(description=None) != _column_hash(description="")

    def test_table_hash_ignores_column_order(self) -> None:
        h1 = _column_hash()
        h2 = _column_hash(column_name="name")
        a = diff.table_content_hash(
            schema_name="public",
            table_name="patients",
            description="Master registry.",
            column_hashes=[h1, h2],
        )
        b = diff.table_content_hash(
            schema_name="public",
            table_name="patients",
            description="Master registry.",
            column_hashes=[h2, h1],
        )
        assert a == b

    def test_table_hash_reflects_column_change(self) -> None:
        base = diff.table_content_hash(
            schema_name="public",
            table_name="patients",
            description="Master registry.",
            column_hashes=[_column_hash()],
        )
        changed = diff.table_content_hash(
            schema_name="public",
            table_name="patients",
            description="Master registry.",
            column_hashes=[_column_hash(description="edited")],
        )
        assert base != changed

    def test_table_hash_reflects_own_fields(self) -> None:
        kwargs: dict[str, Any] = {
            "schema_name": "public",
            "table_name": "patients",
            "description": "Master registry.",
            "column_hashes": [_column_hash()],
        }
        base = diff.table_content_hash(**kwargs)
        assert diff.table_content_hash(**{**kwargs, "description": None}) != base
        assert diff.table_content_hash(**{**kwargs, "table_name": "doctors"}) != base
        assert diff.table_content_hash(**{**kwargs, "schema_name": "other"}) != base

    def test_entity_kinds_never_collide(self) -> None:
        # Same payload under different kinds must hash differently.
        payload = {"term": "UHID", "definition": "x"}
        assert diff.content_hash("glossary", payload) != diff.content_hash(
            "example", payload
        )

    def test_glossary_hash_covers_mapping(self) -> None:
        base = diff.glossary_content_hash(
            term="UHID",
            definition="Unique Health ID",
            maps_to_table="patients",
            maps_to_column=None,
        )
        remapped = diff.glossary_content_hash(
            term="UHID",
            definition="Unique Health ID",
            maps_to_table=None,
            maps_to_column=None,
        )
        assert base != remapped

    def test_example_hash_covers_verification_flag(self) -> None:
        common: dict[str, Any] = {
            "question": "How many patients?",
            "sql_text": "SELECT count(*) FROM patients",
            "tables_used": ["patients"],
        }
        assert diff.example_content_hash(
            **common, is_verified=True
        ) != diff.example_content_hash(**common, is_verified=False)

    def test_hash_version_is_embedded(self) -> None:
        # Guard: bumping HASH_VERSION must invalidate every stored hash.
        assert diff.HASH_VERSION in ("v1",)


class TestDiffRows:
    def test_all_new_rows_are_created(self) -> None:
        result = diff.diff_rows({}, {"a": "h1", "b": "h2"})
        assert result.created == {"a", "b"}
        assert not result.updated and not result.unchanged and not result.removed
        assert result.changed

    def test_identical_hashes_skip(self) -> None:
        existing = {
            "a": diff.RowState(content_hash="h1"),
            "b": diff.RowState(content_hash="h2"),
        }
        result = diff.diff_rows(existing, {"a": "h1", "b": "h2"})
        assert result.unchanged == {"a", "b"}
        assert not result.changed

    def test_hash_mismatch_is_updated(self) -> None:
        existing = {"a": diff.RowState(content_hash="old")}
        result = diff.diff_rows(existing, {"a": "new"})
        assert result.updated == {"a"}
        assert result.changed

    def test_missing_stored_hash_is_updated(self) -> None:
        # Legacy rows ingested before hashing get refreshed exactly once.
        existing = {"a": diff.RowState(content_hash=None)}
        result = diff.diff_rows(existing, {"a": "h1"})
        assert result.updated == {"a"}

    def test_missing_active_row_is_removed_soft_delete(self) -> None:
        existing = {
            "kept": diff.RowState(content_hash="h1"),
            "dropped": diff.RowState(content_hash="h2"),
        }
        result = diff.diff_rows(existing, {"kept": "h1"})
        assert result.removed == {"dropped"}
        assert result.unchanged == {"kept"}

    def test_already_inactive_missing_row_is_unchanged(self) -> None:
        # Second run after a soft-delete must be a no-op, not a re-delete.
        existing = {"gone": diff.RowState(content_hash="h1", is_active=False)}
        result = diff.diff_rows(existing, {})
        assert result.unchanged == {"gone"}
        assert not result.changed

    def test_inactive_row_reappearing_is_updated(self) -> None:
        # Reactivation is a write even when the content hash still matches.
        existing = {"back": diff.RowState(content_hash="h1", is_active=False)}
        result = diff.diff_rows(existing, {"back": "h1"})
        assert result.updated == {"back"}

    def test_empty_fresh_soft_deletes_all_active(self) -> None:
        existing = {
            "a": diff.RowState(content_hash="h1"),
            "b": diff.RowState(content_hash="h2", is_active=False),
        }
        result = diff.diff_rows(existing, {})
        assert result.removed == {"a"}
        assert result.unchanged == {"b"}

    def test_mixed_classification(self) -> None:
        existing = {
            "same": diff.RowState(content_hash="h1"),
            "edited": diff.RowState(content_hash="old"),
            "vanished": diff.RowState(content_hash="h3"),
            "long_gone": diff.RowState(content_hash="h4", is_active=False),
        }
        fresh = {"same": "h1", "edited": "new", "brand_new": "h5"}
        result = diff.diff_rows(existing, fresh)
        assert result.created == {"brand_new"}
        assert result.updated == {"edited"}
        assert result.unchanged == {"same", "long_gone"}
        assert result.removed == {"vanished"}

    def test_second_run_after_apply_reports_unchanged(self) -> None:
        # Simulate run 1 -> apply -> run 2: everything must classify unchanged.
        fresh = {"a": "h1", "b": "h2", "c": "h3"}
        first = diff.diff_rows({}, fresh)
        assert first.created == set(fresh)
        applied = {key: diff.RowState(content_hash=value) for key, value in fresh.items()}
        second = diff.diff_rows(applied, fresh)
        assert second.unchanged == set(fresh)
        assert not second.changed
