"""Per-client analytics aggregation queries.

All public functions accept a ``client_id`` and optional filter parameters.
No raw SQL — SQLAlchemy ORM aggregates only.

Connected statuses   : {"completed"}
Not-connected        : {"no-answer","busy","failed","canceled","cancelled","stopped","error","balance-low"}
Terminal             : connected ∪ not-connected
Pending              : anything not in terminal
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Batch, Call, CallAnalysis
from app.services.dispositions import roll_up_legacy_outcomes
from app.schemas.analytics import (
    AgentStats,
    AnalyticsOverview,
    AnalyticsPeriod,
    BatchStats,
    CallVolumeStats,
    CostStats,
    DurationStats,
    OutcomeBreakdown,
    OutcomeCount,
    RetryStats,
    TimeseriesPoint,
)

CONNECTED = frozenset({"completed"})
NOT_CONNECTED = frozenset(
    {
        "no-answer",
        "busy",
        "failed",
        "canceled",
        "cancelled",
        "stopped",
        "error",
        "balance-low",
    }
)
TERMINAL = CONNECTED | NOT_CONNECTED


def _base_filters(
    client_id: uuid.UUID,
    date_from: datetime | None,
    date_to: datetime | None,
    agent_id: str | None,
    batch_id: uuid.UUID | None,
) -> list[Any]:
    filters: list[Any] = [Call.client_id == client_id]
    if date_from:
        filters.append(Call.created_at >= date_from)
    if date_to:
        filters.append(Call.created_at <= date_to)
    if agent_id:
        filters.append(Call.agent_id == agent_id)
    if batch_id:
        filters.append(Call.batch_id == batch_id)
    stopped_batch_ids = select(Batch.id).where(Batch.status == "stopped")
    filters.append(
        or_(Call.batch_id.is_(None), Call.batch_id.notin_(stopped_batch_ids))
    )
    return filters


def _volume_stats(total: int, connected: int, not_connected: int) -> CallVolumeStats:
    pending = max(total - connected - not_connected, 0)
    return CallVolumeStats(
        total=total,
        connected=connected,
        not_connected=not_connected,
        pending=pending,
        connection_rate=round(connected / total, 4) if total else 0.0,
    )


def _outcome_breakdown(
    outcome_counts: dict[str, int],
    disposition_counts: dict[str, int],
    terminal: int,
) -> OutcomeBreakdown:
    analyzed = sum(outcome_counts.values())
    coverage = round(analyzed / terminal, 4) if terminal else 0.0

    def _one(count: int) -> OutcomeCount:
        return OutcomeCount(
            count=count,
            pct_of_analyzed=round(count / analyzed, 4) if analyzed else 0.0,
        )

    def _as_outcome_counts(counts: dict[str, int]) -> dict[str, OutcomeCount]:
        return {label: _one(count) for label, count in sorted(counts.items())}

    return OutcomeBreakdown(
        analyzed_count=analyzed,
        coverage_pct=coverage,
        by_call_outcome=_as_outcome_counts(outcome_counts),
        by_disposition_status=_as_outcome_counts(disposition_counts),
        **{
            bucket: _one(count)
            for bucket, count in roll_up_legacy_outcomes(outcome_counts).items()
        },
    )


async def _fetch_volume_duration_cost(
    session: AsyncSession, filters: list[Any]
) -> dict[str, Any]:
    connected_expr = case((Call.status.in_(CONNECTED), 1), else_=0)
    not_connected_expr = case((Call.status.in_(NOT_CONNECTED), 1), else_=0)
    connected_cost_expr = case((Call.status.in_(CONNECTED), Call.cost), else_=None)
    retry_expr = case((Call.retry_count > 0, 1), else_=0)
    retry_count_expr = case((Call.retry_count > 0, Call.retry_count), else_=None)

    row = (
        await session.execute(
            select(
                func.count().label("total"),
                func.coalesce(func.sum(connected_expr), 0).label("connected"),
                func.coalesce(func.sum(not_connected_expr), 0).label("not_connected"),
                func.coalesce(func.sum(Call.cost), 0.0).label("total_cost"),
                func.coalesce(func.avg(Call.duration), 0.0).label("avg_duration"),
                func.coalesce(func.sum(Call.duration), 0.0).label("total_duration"),
                func.coalesce(func.avg(connected_cost_expr), 0.0).label(
                    "avg_cost_connected"
                ),
                func.coalesce(func.sum(retry_expr), 0).label("calls_with_retry"),
                func.avg(retry_count_expr).label("avg_retries"),
            ).where(*filters)
        )
    ).one()

    # percentile_cont uses a separate query (ordered-set aggregate)
    p50_row = (
        await session.execute(
            select(
                func.percentile_cont(0.5)
                .within_group(Call.duration.asc())
                .label("p50"),
                func.percentile_cont(0.9)
                .within_group(Call.duration.asc())
                .label("p90"),
            ).where(*filters, Call.duration.isnot(None))
        )
    ).one()

    return {
        "total": int(row.total),
        "connected": int(row.connected),
        "not_connected": int(row.not_connected),
        "total_cost": float(row.total_cost),
        "avg_duration": float(row.avg_duration),
        "total_duration": float(row.total_duration),
        "avg_cost_connected": float(row.avg_cost_connected),
        "calls_with_retry": int(row.calls_with_retry),
        "avg_retries": float(row.avg_retries) if row.avg_retries is not None else None,
        "p50": float(p50_row.p50) if p50_row.p50 is not None else None,
        "p90": float(p50_row.p90) if p50_row.p90 is not None else None,
    }


async def _fetch_outcome_counts(
    session: AsyncSession, filters: list[Any]
) -> dict[str, int]:
    """Rows analysed before the disposition rollout carry no call_outcome — they
    are excluded, so `analyzed_count` counts only rows in the live taxonomy."""
    rows = await session.execute(
        select(CallAnalysis.call_outcome, func.count().label("cnt"))
        .join(Call, Call.id == CallAnalysis.call_id)
        .where(
            *filters,
            Call.status.in_(TERMINAL),
            CallAnalysis.call_outcome.isnot(None),
        )
        .group_by(CallAnalysis.call_outcome)
    )
    return {row.call_outcome: row.cnt for row in rows}


async def _fetch_disposition_counts(
    session: AsyncSession, filters: list[Any]
) -> dict[str, int]:
    """Rows analysed before the disposition rollout have no status — they are
    excluded rather than lumped into a synthetic bucket."""
    rows = await session.execute(
        select(CallAnalysis.disposition_status, func.count().label("cnt"))
        .join(Call, Call.id == CallAnalysis.call_id)
        .where(
            *filters,
            Call.status.in_(TERMINAL),
            CallAnalysis.disposition_status.isnot(None),
        )
        .group_by(CallAnalysis.disposition_status)
    )
    return {row.disposition_status: row.cnt for row in rows}


async def _fetch_not_connected_breakdown(
    session: AsyncSession, filters: list[Any]
) -> dict[str, int]:
    rows = await session.execute(
        select(Call.status, func.count().label("cnt"))
        .where(*filters, Call.status.in_(NOT_CONNECTED))
        .group_by(Call.status)
    )
    return {row.status: row.cnt for row in rows}


def _build_overview(
    agg: dict[str, Any],
    outcome_counts: dict[str, int],
    disposition_counts: dict[str, int],
    nc_breakdown: dict[str, int],
    date_from: datetime | None,
    date_to: datetime | None,
) -> AnalyticsOverview:
    total = agg["total"]
    connected = agg["connected"]
    not_connected = agg["not_connected"]
    avg_per_call = round(agg["total_cost"] / total, 4) if total else 0.0

    return AnalyticsOverview(
        period=AnalyticsPeriod(
            date_from=date_from.isoformat() if date_from else None,
            date_to=date_to.isoformat() if date_to else None,
        ),
        call_volume=_volume_stats(total, connected, not_connected),
        duration=DurationStats(
            total_seconds=round(agg["total_duration"], 2),
            avg_seconds=round(agg["avg_duration"], 2),
            p50_seconds=round(agg["p50"], 2) if agg["p50"] is not None else None,
            p90_seconds=round(agg["p90"], 2) if agg["p90"] is not None else None,
        ),
        cost=CostStats(
            total=round(agg["total_cost"], 4),
            avg_per_call=avg_per_call,
            avg_per_connected=round(agg["avg_cost_connected"], 4),
        ),
        outcomes=_outcome_breakdown(
            outcome_counts, disposition_counts, connected + not_connected
        ),
        not_connected_breakdown=nc_breakdown,
        retry_stats=RetryStats(
            calls_with_retry=agg["calls_with_retry"],
            avg_retries=round(agg["avg_retries"], 2) if agg["avg_retries"] else None,
        ),
    )


async def get_overview(
    session: AsyncSession,
    client_id: uuid.UUID,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    agent_id: str | None = None,
    batch_id: uuid.UUID | None = None,
) -> AnalyticsOverview:
    filters = _base_filters(client_id, date_from, date_to, agent_id, batch_id)
    agg, outcome_counts, disposition_counts, nc_breakdown = (
        await _fetch_volume_duration_cost(session, filters),
        await _fetch_outcome_counts(session, filters),
        await _fetch_disposition_counts(session, filters),
        await _fetch_not_connected_breakdown(session, filters),
    )
    return _build_overview(
        agg, outcome_counts, disposition_counts, nc_breakdown, date_from, date_to
    )


async def get_by_agent(
    session: AsyncSession,
    client_id: uuid.UUID,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    batch_id: uuid.UUID | None = None,
) -> list[AgentStats]:
    base = _base_filters(client_id, date_from, date_to, None, batch_id)

    connected_expr = case((Call.status.in_(CONNECTED), 1), else_=0)
    not_connected_expr = case((Call.status.in_(NOT_CONNECTED), 1), else_=0)
    connected_cost_expr = case((Call.status.in_(CONNECTED), Call.cost), else_=None)

    agg_rows = (
        await session.execute(
            select(
                Call.agent_id,
                func.count().label("total"),
                func.coalesce(func.sum(connected_expr), 0).label("connected"),
                func.coalesce(func.sum(not_connected_expr), 0).label("not_connected"),
                func.coalesce(func.sum(Call.cost), 0.0).label("total_cost"),
                func.coalesce(func.sum(Call.duration), 0.0).label("total_duration"),
                func.coalesce(func.avg(Call.duration), 0.0).label("avg_duration"),
                func.coalesce(func.avg(connected_cost_expr), 0.0).label(
                    "avg_cost_connected"
                ),
            )
            .where(*base)
            .group_by(Call.agent_id)
        )
    ).all()

    if not agg_rows:
        return []

    pct_rows = (
        await session.execute(
            select(
                Call.agent_id,
                func.percentile_cont(0.5)
                .within_group(Call.duration.asc())
                .label("p50"),
                func.percentile_cont(0.9)
                .within_group(Call.duration.asc())
                .label("p90"),
            )
            .where(*base, Call.duration.isnot(None))
            .group_by(Call.agent_id)
        )
    ).all()
    pct_by_agent: dict[str, tuple[Any, Any]] = {
        r.agent_id: (r.p50, r.p90) for r in pct_rows
    }

    outcome_rows = (
        await session.execute(
            select(Call.agent_id, CallAnalysis.call_outcome, func.count().label("cnt"))
            .join(CallAnalysis, Call.id == CallAnalysis.call_id)
            .where(
                *base,
                Call.status.in_(TERMINAL),
                CallAnalysis.call_outcome.isnot(None),
            )
            .group_by(Call.agent_id, CallAnalysis.call_outcome)
        )
    ).all()
    outcomes_by_agent: dict[str, dict[str, int]] = {}
    for r in outcome_rows:
        outcomes_by_agent.setdefault(r.agent_id, {})[r.call_outcome] = r.cnt

    disposition_rows = (
        await session.execute(
            select(
                Call.agent_id,
                CallAnalysis.disposition_status,
                func.count().label("cnt"),
            )
            .join(CallAnalysis, Call.id == CallAnalysis.call_id)
            .where(
                *base,
                Call.status.in_(TERMINAL),
                CallAnalysis.disposition_status.isnot(None),
            )
            .group_by(Call.agent_id, CallAnalysis.disposition_status)
        )
    ).all()
    dispositions_by_agent: dict[str, dict[str, int]] = {}
    for r in disposition_rows:
        dispositions_by_agent.setdefault(r.agent_id, {})[r.disposition_status] = r.cnt

    results: list[AgentStats] = []
    for row in agg_rows:
        p50, p90 = pct_by_agent.get(row.agent_id, (None, None))
        avg_per_call = (
            round(float(row.total_cost) / int(row.total), 4) if row.total else 0.0
        )
        terminal = int(row.connected) + int(row.not_connected)
        results.append(
            AgentStats(
                agent_id=row.agent_id,
                call_volume=_volume_stats(
                    int(row.total), int(row.connected), int(row.not_connected)
                ),
                duration=DurationStats(
                    total_seconds=round(float(row.total_duration), 2),
                    avg_seconds=round(float(row.avg_duration), 2),
                    p50_seconds=round(float(p50), 2) if p50 is not None else None,
                    p90_seconds=round(float(p90), 2) if p90 is not None else None,
                ),
                cost=CostStats(
                    total=round(float(row.total_cost), 4),
                    avg_per_call=avg_per_call,
                    avg_per_connected=round(float(row.avg_cost_connected), 4),
                ),
                outcomes=_outcome_breakdown(
                    outcomes_by_agent.get(row.agent_id, {}),
                    dispositions_by_agent.get(row.agent_id, {}),
                    terminal,
                ),
            )
        )
    return results


async def get_by_batch(
    session: AsyncSession,
    client_id: uuid.UUID,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    agent_id: str | None = None,
) -> list[BatchStats]:
    base = _base_filters(client_id, date_from, date_to, agent_id, None)
    base_with_batch: list[Any] = [*base, Call.batch_id.isnot(None)]

    connected_expr = case((Call.status.in_(CONNECTED), 1), else_=0)
    not_connected_expr = case((Call.status.in_(NOT_CONNECTED), 1), else_=0)
    connected_cost_expr = case((Call.status.in_(CONNECTED), Call.cost), else_=None)

    # Aggregate stats + batch metadata in one JOIN — eliminates per-batch session.get()
    agg_rows = (
        await session.execute(
            select(
                Batch.id.label("batch_pk"),
                Batch.voice_batch_id,
                Batch.status.label("batch_status"),
                Batch.scheduled_at,
                Batch.total_count,
                func.count().label("total"),
                func.coalesce(func.sum(connected_expr), 0).label("connected"),
                func.coalesce(func.sum(not_connected_expr), 0).label("not_connected"),
                func.coalesce(func.sum(Call.cost), 0.0).label("total_cost"),
                func.coalesce(func.sum(Call.duration), 0.0).label("total_duration"),
                func.coalesce(func.avg(Call.duration), 0.0).label("avg_duration"),
                func.coalesce(func.avg(connected_cost_expr), 0.0).label(
                    "avg_cost_connected"
                ),
            )
            .join(Batch, Batch.id == Call.batch_id)
            .where(*base_with_batch)
            .group_by(
                Batch.id,
                Batch.voice_batch_id,
                Batch.status,
                Batch.scheduled_at,
                Batch.total_count,
            )
        )
    ).all()

    if not agg_rows:
        return []

    batch_pks = [row.batch_pk for row in agg_rows]

    pct_rows = (
        await session.execute(
            select(
                Call.batch_id,
                func.percentile_cont(0.5)
                .within_group(Call.duration.asc())
                .label("p50"),
                func.percentile_cont(0.9)
                .within_group(Call.duration.asc())
                .label("p90"),
            )
            .where(
                *base_with_batch,
                Call.duration.isnot(None),
                Call.batch_id.in_(batch_pks),
            )
            .group_by(Call.batch_id)
        )
    ).all()
    pct_by_batch: dict[uuid.UUID, tuple[Any, Any]] = {
        r.batch_id: (r.p50, r.p90) for r in pct_rows
    }

    outcome_rows = (
        await session.execute(
            select(Call.batch_id, CallAnalysis.call_outcome, func.count().label("cnt"))
            .join(CallAnalysis, Call.id == CallAnalysis.call_id)
            .where(
                *base_with_batch,
                Call.status.in_(TERMINAL),
                Call.batch_id.in_(batch_pks),
                CallAnalysis.call_outcome.isnot(None),
            )
            .group_by(Call.batch_id, CallAnalysis.call_outcome)
        )
    ).all()
    outcomes_by_batch: dict[uuid.UUID, dict[str, int]] = {}
    for r in outcome_rows:
        outcomes_by_batch.setdefault(r.batch_id, {})[r.call_outcome] = r.cnt

    disposition_rows = (
        await session.execute(
            select(
                Call.batch_id,
                CallAnalysis.disposition_status,
                func.count().label("cnt"),
            )
            .join(CallAnalysis, Call.id == CallAnalysis.call_id)
            .where(
                *base_with_batch,
                Call.status.in_(TERMINAL),
                Call.batch_id.in_(batch_pks),
                CallAnalysis.disposition_status.isnot(None),
            )
            .group_by(Call.batch_id, CallAnalysis.disposition_status)
        )
    ).all()
    dispositions_by_batch: dict[uuid.UUID, dict[str, int]] = {}
    for r in disposition_rows:
        dispositions_by_batch.setdefault(r.batch_id, {})[r.disposition_status] = r.cnt

    results: list[BatchStats] = []
    for row in agg_rows:
        p50, p90 = pct_by_batch.get(row.batch_pk, (None, None))
        avg_per_call = (
            round(float(row.total_cost) / int(row.total), 4) if row.total else 0.0
        )
        terminal = int(row.connected) + int(row.not_connected)
        results.append(
            BatchStats(
                batch_id=row.voice_batch_id,
                batch_status=row.batch_status,
                scheduled_at=row.scheduled_at,
                total_recipients=row.total_count,
                call_volume=_volume_stats(
                    int(row.total), int(row.connected), int(row.not_connected)
                ),
                duration=DurationStats(
                    total_seconds=round(float(row.total_duration), 2),
                    avg_seconds=round(float(row.avg_duration), 2),
                    p50_seconds=round(float(p50), 2) if p50 is not None else None,
                    p90_seconds=round(float(p90), 2) if p90 is not None else None,
                ),
                cost=CostStats(
                    total=round(float(row.total_cost), 4),
                    avg_per_call=avg_per_call,
                    avg_per_connected=round(float(row.avg_cost_connected), 4),
                ),
                outcomes=_outcome_breakdown(
                    outcomes_by_batch.get(row.batch_pk, {}),
                    dispositions_by_batch.get(row.batch_pk, {}),
                    terminal,
                ),
            )
        )
    return results


async def get_timeseries(
    session: AsyncSession,
    client_id: uuid.UUID,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    agent_id: str | None = None,
    batch_id: uuid.UUID | None = None,
    granularity: str = "day",
) -> list[TimeseriesPoint]:
    trunc = "day" if granularity not in {"day", "week"} else granularity
    filters = _base_filters(client_id, date_from, date_to, agent_id, batch_id)

    connected_expr = case((Call.status.in_(CONNECTED), 1), else_=0)
    not_connected_expr = case((Call.status.in_(NOT_CONNECTED), 1), else_=0)
    bucket = func.date_trunc(trunc, Call.created_at).label("bucket")

    volume_rows = await session.execute(
        select(
            bucket,
            func.count().label("total"),
            func.sum(connected_expr).label("connected"),
            func.sum(not_connected_expr).label("not_connected"),
        )
        .where(*filters)
        .group_by(text("bucket"))
        .order_by(text("bucket"))
    )

    points_by_date: dict[str, TimeseriesPoint] = {}
    for row in volume_rows:
        date_str = row.bucket.date().isoformat()
        points_by_date[date_str] = TimeseriesPoint(
            date=date_str,
            total=int(row.total),
            connected=int(row.connected or 0),
            not_connected=int(row.not_connected or 0),
            by_call_outcome={},
            by_disposition_status={},
        )

    # Both resolutions come from one pass: disposition_status is stored alongside
    # call_outcome, so grouping by the pair avoids a second round trip.
    outcome_rows = await session.execute(
        select(
            func.date_trunc(trunc, Call.created_at).label("bucket"),
            CallAnalysis.call_outcome,
            CallAnalysis.disposition_status,
            func.count().label("cnt"),
        )
        .join(Call, Call.id == CallAnalysis.call_id)
        .where(*filters, CallAnalysis.call_outcome.isnot(None))
        .group_by(
            text("bucket"), CallAnalysis.call_outcome, CallAnalysis.disposition_status
        )
        .order_by(text("bucket"))
    )
    for row in outcome_rows:
        date_str = row.bucket.date().isoformat()
        point = points_by_date.get(date_str)
        if point is None:
            continue
        count = int(row.cnt)
        point.by_call_outcome[row.call_outcome] = (
            point.by_call_outcome.get(row.call_outcome, 0) + count
        )
        if row.disposition_status is not None:
            point.by_disposition_status[row.disposition_status] = (
                point.by_disposition_status.get(row.disposition_status, 0) + count
            )

    for point in points_by_date.values():
        point.outcomes = roll_up_legacy_outcomes(point.by_call_outcome)
    return list(points_by_date.values())
