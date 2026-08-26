from __future__ import annotations

from app.sql_agent.schema_context import load_catalog


def test_table_subset_keeps_enriched_column_values() -> None:
    subset = load_catalog("kalaam").render_table_subset(
        ["patient_visits", "visits_actions"]
    )

    assert "values: cancelled, completed, pending, scheduled" in subset
    assert "values: follow_up, ip_admission, lab_test, medication" in subset
    assert "- department -" in subset


def test_pruned_table_subset_keeps_selected_column_values() -> None:
    subset = load_catalog("kalaam").render_table_subset(
        ["visits_actions"],
        {
            "visits_actions": [
                "action_type",
                "status",
                "urgency",
                "revenue_potential",
            ]
        },
    )

    assert "Available columns: action_type, revenue_potential, status, urgency" in subset
    assert "values: cancelled, completed, pending, scheduled" in subset
    assert "values: follow_up, ip_admission, lab_test, medication" in subset
    assert "- title -" not in subset
