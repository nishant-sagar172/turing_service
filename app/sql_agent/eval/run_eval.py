"""Smoke evaluation harness for the SQL Builder Agent."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.sql_agent.config import get_sql_agent_settings
from app.sql_agent.pipeline import build_query
from app.sql_agent.schema_context import load_catalog
from app.sql_agent.schemas import BuildStatus


class EvalCase(BaseModel):
    question: str = Field(min_length=1)
    expected_tables: list[str] = Field(default_factory=list)
    expected_sql_shape: list[str] = Field(default_factory=list)
    expected_status: BuildStatus | None = None


class EvalSet(BaseModel):
    cases: list[EvalCase] = Field(default_factory=list)


async def run_eval(workspace: str) -> int:
    settings = get_sql_agent_settings()
    path = Path(__file__).with_name("golden_set.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    eval_set = EvalSet.model_validate(raw)
    catalog = load_catalog(workspace)

    total = len(eval_set.cases)
    built = 0
    status_matches = 0
    table_scores: list[float] = []
    shape_matches = 0

    for case in eval_set.cases:
        response = await build_query(
            case.question,
            workspace=workspace,
            settings=settings,
        )
        if response.status == "built":
            built += 1
        if case.expected_status is None or response.status == case.expected_status:
            status_matches += 1
        if case.expected_tables:
            expected = set(case.expected_tables)
            actual = set(response.tables_used)
            table_scores.append(len(expected & actual) / len(expected))
        if response.sql and all(
            token.lower() in response.sql.lower() for token in case.expected_sql_shape
        ):
            shape_matches += 1

    average_table_overlap = (
        sum(table_scores) / len(table_scores) if table_scores else 0.0
    )
    print(f"workspace: {catalog.summary()}")
    print(f"cases: {total}")
    print(f"built: {built}")
    print(f"status_match_rate: {status_matches / total:.2f}")
    print(f"table_overlap: {average_table_overlap:.2f}")
    print(f"shape_matches: {shape_matches}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SQL-agent golden-set evaluation.")
    parser.add_argument("--workspace", default="kalaam")
    args = parser.parse_args()
    return asyncio.run(run_eval(args.workspace))


if __name__ == "__main__":
    raise SystemExit(main())
