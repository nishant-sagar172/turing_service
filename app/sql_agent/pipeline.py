"""Plain async orchestration for natural-language to validated SQL."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from datetime import date
from typing import Protocol, TypeVar, cast
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy import text

from app.sql_agent.config import SqlAgentSettings
from app.sql_agent.llm import LLMError, ModelTier, get_chat_model, model_name_for_tier
from app.sql_agent.prompts import (
    AMBIGUITY_CHECK,
    COLUMN_PRUNE,
    PROMPT_ENHANCE,
    PROMPT_VERSIONS,
    SQL_CRITIC,
    SQL_GENERATE,
    SQL_REPAIR,
    TABLE_SELECT,
    SQL_VOTE,
)
from app.sql_agent.schema_context import SchemaCatalog, load_catalog
from app.sql_agent.schemas import BuildQueryResponse
from app.sql_agent.target_db import target_session
from app.sql_agent.validation import GuardError, guard_sql

logger = logging.getLogger("turing.sql_agent")

_SUPPORTED_WORKSPACE = "kalaam"
_DEFAULT_DIALECT = "postgresql"

T = TypeVar("T", bound=BaseModel)


class _StructuredRunnable(Protocol):
    async def ainvoke(self, input_text: str) -> object: ...


class _ExplainValidationError(ValueError):
    """The guarded SQL reached Postgres planning and was rejected."""


class _PromptEnhanceResult(BaseModel):
    enhanced_question: str = Field(min_length=1)
    write_intent: bool = False
    reason: str | None = None


class _AmbiguityResult(BaseModel):
    clarify_needed: bool = False
    clarifying_question: str | None = None
    reason: str | None = None


class _TableSelectResult(BaseModel):
    tables: list[str] = Field(default_factory=list)
    rationale: str | None = None

    @field_validator("tables")
    @classmethod
    def _normalize_tables(cls, value: list[str]) -> list[str]:
        return [_normalize_identifier(item) for item in value if item.strip()]


class _TableColumns(BaseModel):
    table: str
    columns: list[str] = Field(default_factory=list)

    @field_validator("table")
    @classmethod
    def _normalize_table(cls, value: str) -> str:
        return _normalize_identifier(value)

    @field_validator("columns")
    @classmethod
    def _normalize_columns(cls, value: list[str]) -> list[str]:
        return [_normalize_identifier(item) for item in value if item.strip()]


class _ColumnPruneResult(BaseModel):
    tables: list[_TableColumns] = Field(default_factory=list)


class _SqlCandidate(BaseModel):
    sql: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    tables_used: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("tables_used")
    @classmethod
    def _normalize_tables(cls, value: list[str]) -> list[str]:
        return [_normalize_identifier(item) for item in value if item.strip()]


class _VoteResult(BaseModel):
    best_index: int = Field(ge=0)
    reason: str | None = None


class _CriticResult(BaseModel):
    approved: bool
    notes: str = Field(min_length=1)


class _RepairResult(BaseModel):
    sql: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


async def build_query(
    question: str,
    *,
    workspace: str,
    settings: SqlAgentSettings,
    audit_client_id: UUID | None = None,
) -> BuildQueryResponse:
    if workspace != _SUPPORTED_WORKSPACE:
        return BuildQueryResponse(
            status="clarify_needed",
            dialect=_DEFAULT_DIALECT,
            clarifying_question=f"Workspace {workspace!r} is not available for SQL generation.",
            reason="unsupported_workspace",
        )

    catalog = load_catalog(workspace)
    enhanced = await _prompt_enhance(question, catalog, settings)
    if enhanced.write_intent:
        response = BuildQueryResponse(
            status="blocked",
            dialect=catalog.dialect,
            reason=enhanced.reason or "Write intent is not allowed.",
        )
        _audit(catalog, question, enhanced.enhanced_question, response, audit_client_id, settings, 0)
        return response

    ambiguity = await _ambiguity_check(enhanced.enhanced_question, catalog, settings)
    if ambiguity.clarify_needed:
        response = BuildQueryResponse(
            status="clarify_needed",
            dialect=catalog.dialect,
            clarifying_question=ambiguity.clarifying_question,
            reason=ambiguity.reason,
        )
        _audit(catalog, question, enhanced.enhanced_question, response, audit_client_id, settings, 0)
        return response

    selected_tables = await _select_tables(enhanced.enhanced_question, catalog, settings)
    if not selected_tables:
        response = BuildQueryResponse(
            status="clarify_needed",
            dialect=catalog.dialect,
            clarifying_question="Which part of Kalaam should this question use?",
            reason="no_known_tables_selected",
        )
        _audit(catalog, question, enhanced.enhanced_question, response, audit_client_id, settings, 0)
        return response

    selected_schema = await _build_selected_schema(
        enhanced.enhanced_question,
        selected_tables,
        catalog,
        settings,
    )
    candidate = await _generate_sql(
        enhanced.enhanced_question,
        selected_schema,
        settings,
        candidate_instruction="Generate the strongest single answer.",
    )
    if candidate.confidence < settings.sql_agent_confidence_threshold:
        candidate = await _multi_candidate_vote(
            enhanced.enhanced_question,
            selected_schema,
            settings,
            first_candidate=candidate,
        )

    critic = await _critic(enhanced.enhanced_question, selected_schema, candidate.sql, settings)
    repair_attempts = 0
    current_sql = candidate.sql
    explanation = candidate.explanation
    confidence = candidate.confidence
    critic_notes = critic.notes

    if not critic.approved:
        if settings.sql_agent_max_repair_attempts <= 0:
            response = _repair_exhausted(catalog, critic_notes)
            _audit(
                catalog,
                question,
                enhanced.enhanced_question,
                response,
                audit_client_id,
                settings,
                repair_attempts,
            )
            return response
        repair_attempts += 1
        repaired = await _repair_sql(
            enhanced.enhanced_question,
            selected_schema,
            current_sql,
            f"semantic_critic: {critic.notes}",
            settings,
        )
        current_sql = repaired.sql
        explanation = repaired.explanation
        confidence = repaired.confidence

    while True:
        validation_error: str | None = None
        try:
            guard = guard_sql(
                current_sql,
                catalog.allowlist,
                default_row_limit=settings.sql_agent_default_row_limit,
                default_schema=catalog.default_schema,
            )
            await _explain_if_enabled(guard.sql, catalog, settings)
        except GuardError as exc:
            validation_error = f"{exc.code.value}: {exc}"
        except _ExplainValidationError as exc:
            validation_error = f"explain_error: {exc}"
        else:
            final_critic = await _critic(
                enhanced.enhanced_question,
                selected_schema,
                guard.sql,
                settings,
            )
            critic_notes = final_critic.notes
            if not final_critic.approved:
                validation_error = f"semantic_critic: {final_critic.notes}"
                if repair_attempts >= settings.sql_agent_max_repair_attempts:
                    response = _repair_exhausted(catalog, validation_error)
                    _audit(
                        catalog,
                        question,
                        enhanced.enhanced_question,
                        response,
                        audit_client_id,
                        settings,
                        repair_attempts,
                    )
                    return response

                repair_attempts += 1
                repaired = await _repair_sql(
                    enhanced.enhanced_question,
                    selected_schema,
                    guard.sql,
                    validation_error,
                    settings,
                )
                current_sql = repaired.sql
                explanation = repaired.explanation
                confidence = repaired.confidence
                continue

            response = BuildQueryResponse(
                status="built",
                sql=guard.sql,
                dialect=catalog.dialect,
                validated=True,
                explanation=explanation,
                tables_used=list(guard.tables_used),
                confidence=confidence,
                critic_notes=critic_notes,
            )
            _audit(
                catalog,
                question,
                enhanced.enhanced_question,
                response,
                audit_client_id,
                settings,
                repair_attempts,
            )
            return response

        if repair_attempts >= settings.sql_agent_max_repair_attempts:
            response = _repair_exhausted(catalog, validation_error)
            _audit(
                catalog,
                question,
                enhanced.enhanced_question,
                response,
                audit_client_id,
                settings,
                repair_attempts,
            )
            return response

        repair_attempts += 1
        repaired = await _repair_sql(
            enhanced.enhanced_question,
            selected_schema,
            current_sql,
            validation_error,
            settings,
        )
        current_sql = repaired.sql
        explanation = repaired.explanation
        confidence = repaired.confidence


async def _prompt_enhance(
    question: str,
    catalog: SchemaCatalog,
    settings: SqlAgentSettings,
) -> _PromptEnhanceResult:
    prompt = PROMPT_ENHANCE.render(
        current_date=date.today().isoformat(),
        catalog=catalog.prompt_catalog,
        question=question,
    )
    return await _invoke_structured(prompt, _PromptEnhanceResult, "select", settings)


async def _ambiguity_check(
    enhanced_question: str,
    catalog: SchemaCatalog,
    settings: SqlAgentSettings,
) -> _AmbiguityResult:
    prompt = AMBIGUITY_CHECK.render(
        catalog=catalog.prompt_catalog,
        enhanced_question=enhanced_question,
    )
    return await _invoke_structured(prompt, _AmbiguityResult, "select", settings)


async def _select_tables(
    enhanced_question: str,
    catalog: SchemaCatalog,
    settings: SqlAgentSettings,
) -> list[str]:
    prompt = TABLE_SELECT.render(
        catalog=catalog.prompt_catalog,
        enhanced_question=enhanced_question,
    )
    result = await _invoke_structured(prompt, _TableSelectResult, "select", settings)
    selected: list[str] = []
    for table_name in result.tables:
        if table_name in catalog.allowlist and table_name not in selected:
            selected.append(table_name)
    return selected


async def _build_selected_schema(
    enhanced_question: str,
    selected_tables: list[str],
    catalog: SchemaCatalog,
    settings: SqlAgentSettings,
) -> str:
    selected_schema = catalog.render_table_subset(selected_tables)
    prompt = COLUMN_PRUNE.render(
        selected_schema=selected_schema,
        enhanced_question=enhanced_question,
    )
    result = await _invoke_structured(prompt, _ColumnPruneResult, "prune", settings)
    pruned = _pruned_columns(result, selected_tables, catalog)
    return catalog.render_table_subset(selected_tables, pruned)


async def _generate_sql(
    enhanced_question: str,
    selected_schema: str,
    settings: SqlAgentSettings,
    *,
    candidate_instruction: str,
) -> _SqlCandidate:
    prompt = SQL_GENERATE.render(
        selected_schema=selected_schema,
        enhanced_question=enhanced_question,
        candidate_instruction=candidate_instruction,
    )
    return await _invoke_structured(prompt, _SqlCandidate, "generate", settings)


async def _multi_candidate_vote(
    enhanced_question: str,
    selected_schema: str,
    settings: SqlAgentSettings,
    *,
    first_candidate: _SqlCandidate,
) -> _SqlCandidate:
    candidates = [first_candidate]
    count = max(settings.sql_agent_multi_candidate_count, 1)
    for index in range(1, count):
        candidates.append(
            await _generate_sql(
                enhanced_question,
                selected_schema,
                settings,
                candidate_instruction=f"Generate alternative candidate {index + 1}.",
            )
        )
    if len(candidates) == 1:
        return first_candidate

    prompt = SQL_VOTE.render(
        selected_schema=selected_schema,
        enhanced_question=enhanced_question,
        candidates=_render_candidates(candidates),
    )
    vote = await _invoke_structured(prompt, _VoteResult, "critic", settings)
    if vote.best_index >= len(candidates):
        return first_candidate
    return candidates[vote.best_index]


async def _critic(
    enhanced_question: str,
    selected_schema: str,
    sql: str,
    settings: SqlAgentSettings,
) -> _CriticResult:
    prompt = SQL_CRITIC.render(
        selected_schema=selected_schema,
        enhanced_question=enhanced_question,
        sql=sql,
    )
    return await _invoke_structured(prompt, _CriticResult, "critic", settings)


async def _repair_sql(
    enhanced_question: str,
    selected_schema: str,
    sql: str,
    error: str,
    settings: SqlAgentSettings,
) -> _RepairResult:
    prompt = SQL_REPAIR.render(
        selected_schema=selected_schema,
        enhanced_question=enhanced_question,
        sql=sql,
        error=error,
    )
    return await _invoke_structured(prompt, _RepairResult, "repair", settings)


async def _invoke_structured(
    prompt: str,
    output_model: type[T],
    tier: ModelTier,
    settings: SqlAgentSettings,
) -> T:
    model_name = model_name_for_tier(settings, tier)
    try:
        model = get_chat_model(tier, settings)
        runnable = cast(_StructuredRunnable, model.with_structured_output(output_model))
        result = await runnable.ainvoke(prompt)
        if isinstance(result, output_model):
            return result
        return output_model.model_validate(result)
    except (ValidationError, TypeError, ValueError) as exc:
        raise LLMError(
            f"Model {model_name!r} returned an invalid structured response.",
            provider=_provider_name(model_name),
        ) from exc
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(
            f"Model {model_name!r} failed during SQL-agent stage {tier!r}.",
            provider=_provider_name(model_name),
        ) from exc


async def _explain_if_enabled(
    sql: str,
    catalog: SchemaCatalog,
    settings: SqlAgentSettings,
) -> None:
    if not settings.sql_agent_explain_validation:
        return
    _seed_target_connection(catalog, settings)
    async with target_session(
        catalog.connection_env_var,
        statement_timeout_ms=settings.sql_agent_statement_timeout_ms,
    ) as session:
        try:
            await session.execute(text(f"EXPLAIN {sql}"))
        except sqlalchemy_exc.OperationalError:
            raise
        except sqlalchemy_exc.SQLAlchemyError as exc:
            raise _ExplainValidationError(str(exc)) from exc


def _seed_target_connection(catalog: SchemaCatalog, settings: SqlAgentSettings) -> None:
    if catalog.connection_env_var == "KALAAM_READONLY_DATABASE_URL":
        os.environ.setdefault(catalog.connection_env_var, settings.kalaam_readonly_database_url)


def _pruned_columns(
    result: _ColumnPruneResult,
    selected_tables: list[str],
    catalog: SchemaCatalog,
) -> dict[str, list[str]]:
    selected = set(selected_tables)
    pruned: dict[str, list[str]] = {}
    for item in result.tables:
        if item.table not in selected:
            continue
        valid_columns = [
            column
            for column in item.columns
            if column in catalog.allowlist[item.table]
        ]
        if valid_columns:
            pruned[item.table] = sorted(set(valid_columns))
    return pruned


def _render_candidates(candidates: Sequence[_SqlCandidate]) -> str:
    rendered: list[str] = []
    for index, candidate in enumerate(candidates):
        rendered.append(f"[{index}] confidence={candidate.confidence}")
        rendered.append(candidate.sql)
        rendered.append(candidate.explanation)
    return "\n".join(rendered)


def _repair_exhausted(catalog: SchemaCatalog, reason: str | None) -> BuildQueryResponse:
    return BuildQueryResponse(
        status="repair_exhausted",
        dialect=catalog.dialect,
        validated=False,
        reason=reason or "Could not produce valid SQL within the repair budget.",
        critic_notes=reason,
    )


def _audit(
    catalog: SchemaCatalog,
    question: str,
    enhanced_question: str,
    response: BuildQueryResponse,
    audit_client_id: UUID | None,
    settings: SqlAgentSettings,
    repair_attempts: int,
) -> None:
    payload: dict[str, object] = {
        "client_id": str(audit_client_id) if audit_client_id else None,
        "workspace": catalog.workspace,
        "question": question,
        "enhanced_question": enhanced_question,
        "status": response.status,
        "selected_tables": response.tables_used,
        "final_sql": response.sql,
        "repair_attempts": repair_attempts,
        "model_versions": {
            "generate": settings.sql_agent_model_generate,
            "select": settings.sql_agent_model_select,
            "prune": settings.sql_agent_model_prune,
            "critic": settings.sql_agent_model_critic,
            "repair": settings.sql_agent_model_repair,
        },
        "prompt_versions": PROMPT_VERSIONS,
    }
    logger.info("sql_agent_audit %s", json.dumps(payload, sort_keys=True))


def _provider_name(model_name: str) -> str | None:
    if ":" not in model_name:
        return None
    return model_name.split(":", 1)[0]


def _normalize_identifier(value: str) -> str:
    return value.strip().strip('"`').lower()
