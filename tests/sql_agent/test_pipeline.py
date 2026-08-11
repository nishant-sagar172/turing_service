from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from app.sql_agent.config import SqlAgentSettings
from app.sql_agent import pipeline


def _settings() -> SqlAgentSettings:
    return SqlAgentSettings(
        sql_agent_explain_validation=False,
        sql_agent_max_repair_attempts=1,
        sql_agent_confidence_threshold=0.7,
        sql_agent_multi_candidate_count=2,
    )


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _patch_structured(monkeypatch: Any, responses: Iterable[Any]) -> list[str]:
    calls: list[str] = []
    iterator = iter(responses)

    async def fake_invoke(
        prompt: str,
        output_model: type[Any],
        tier: pipeline.ModelTier,
        settings: SqlAgentSettings,
    ) -> Any:
        calls.append(output_model.__name__)
        response = next(iterator)
        if isinstance(response, output_model):
            return response
        return output_model.model_validate(response)

    monkeypatch.setattr(pipeline, "_invoke_structured", fake_invoke)
    return calls


def test_build_query_happy_path_returns_validated_sql(monkeypatch: Any) -> None:
    calls = _patch_structured(
        monkeypatch,
        [
            {"enhanced_question": "How many patients registered last month?"},
            {"clarify_needed": False},
            {"tables": ["patients"]},
            {"tables": [{"table": "patients", "columns": ["id", "created_at"]}]},
            {
                "sql": "SELECT COUNT(*) AS patient_count FROM patients",
                "explanation": "Counts patients.",
                "tables_used": ["patients"],
                "confidence": 0.9,
            },
            {"approved": True, "notes": "Looks correct."},
            {"approved": True, "notes": "Still correct."},
        ],
    )

    response = _run(
        pipeline.build_query(
            "How many patients registered last month?",
            workspace="kalaam",
            settings=_settings(),
        )
    )

    assert response.status == "built"
    assert response.validated is True
    assert response.sql == "SELECT COUNT(*) AS patient_count FROM patients LIMIT 200"
    assert response.tables_used == ["patients"]
    assert calls == [
        "_PromptEnhanceResult",
        "_AmbiguityResult",
        "_TableSelectResult",
        "_ColumnPruneResult",
        "_SqlCandidate",
        "_CriticResult",
        "_CriticResult",
    ]


def test_build_query_blocks_write_intent_before_later_stages(monkeypatch: Any) -> None:
    calls = _patch_structured(
        monkeypatch,
        [
            {
                "enhanced_question": "Delete all patients.",
                "write_intent": True,
                "reason": "Write intent is not allowed.",
            },
        ],
    )

    response = _run(
        pipeline.build_query(
            "Delete all patients.",
            workspace="kalaam",
            settings=_settings(),
        )
    )

    assert response.status == "blocked"
    assert response.sql is None
    assert response.reason == "Write intent is not allowed."
    assert calls == ["_PromptEnhanceResult"]


def test_build_query_returns_clarify_needed_for_ambiguous_question(monkeypatch: Any) -> None:
    calls = _patch_structured(
        monkeypatch,
        [
            {"enhanced_question": "Show me the report."},
            {
                "clarify_needed": True,
                "clarifying_question": "Which report do you need?",
                "reason": "underspecified_metric",
            },
        ],
    )

    response = _run(
        pipeline.build_query(
            "Show me the report.",
            workspace="kalaam",
            settings=_settings(),
        )
    )

    assert response.status == "clarify_needed"
    assert response.clarifying_question == "Which report do you need?"
    assert response.sql is None
    assert calls == ["_PromptEnhanceResult", "_AmbiguityResult"]


def test_build_query_repairs_guard_failure(monkeypatch: Any) -> None:
    _patch_structured(
        monkeypatch,
        [
            {"enhanced_question": "Count patients."},
            {"clarify_needed": False},
            {"tables": ["patients"]},
            {"tables": [{"table": "patients", "columns": ["id"]}]},
            {
                "sql": "SELECT made_up_column FROM patients",
                "explanation": "Initial attempt.",
                "tables_used": ["patients"],
                "confidence": 0.9,
            },
            {"approved": True, "notes": "Looks okay semantically."},
            {
                "sql": "SELECT COUNT(*) AS patient_count FROM patients",
                "explanation": "Corrected count.",
                "confidence": 0.8,
            },
            {"approved": True, "notes": "Corrected query is good."},
        ],
    )

    response = _run(
        pipeline.build_query(
            "Count patients.",
            workspace="kalaam",
            settings=_settings(),
        )
    )

    assert response.status == "built"
    assert response.sql == "SELECT COUNT(*) AS patient_count FROM patients LIMIT 200"
    assert response.explanation == "Corrected count."


def test_build_query_returns_repair_exhausted_when_repair_budget_fails(
    monkeypatch: Any,
) -> None:
    _patch_structured(
        monkeypatch,
        [
            {"enhanced_question": "Count patients."},
            {"clarify_needed": False},
            {"tables": ["patients"]},
            {"tables": [{"table": "patients", "columns": ["id"]}]},
            {
                "sql": "SELECT made_up_column FROM patients",
                "explanation": "Initial attempt.",
                "tables_used": ["patients"],
                "confidence": 0.9,
            },
            {"approved": True, "notes": "Looks okay semantically."},
            {
                "sql": "SELECT still_wrong FROM patients",
                "explanation": "Still invalid.",
                "confidence": 0.4,
            },
        ],
    )

    response = _run(
        pipeline.build_query(
            "Count patients.",
            workspace="kalaam",
            settings=_settings(),
        )
    )

    assert response.status == "repair_exhausted"
    assert response.sql is None
    assert response.validated is False
    assert response.reason is not None
