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

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Batch, Call, CallAnalysis
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
NOT_CONNECTED = frozenset({
    "no-answer", "busy", "failed", "canceled", "cancelled",
    "stopped", "error", "balance-low",
})
TERMINAL = CONNECTED | NOT_CONNECTED
OUTCOME_BUCKETS = ["booking", "escalation", "not_interested", "no_output", "follow_up", "other"]


def _base_filters(
    client_id: uuid.UUID,
    date_from: datetime | None,
    date_to: datetime | None,
    agent_id: str | None,
    batch_id: uuid.UUID | None,
) -> list:
    filters: list = [Call.client_id == client_id]
    if date_from:
        filters.append(Call.created_at >= date_from)
    if date_to:
        filters.append(Call.created_at <= date_to)
    if agent_id:
        filters.append(Call.agent_id == agent_id)
    if batch_id:
        filters.append(Call.batch_id == batch_id)
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


def _outcome_breakdown(outcome_counts: dict[str, int], connected: int) -> OutcomeBreakdown:
    analyzed = sum(outcome_counts.values())
    coverage = round(analyzed / connected, 4) if connected else 0.0

    def _oc(bucket: str) -> OutcomeCount:
        count = outcome_counts.get(bucket, 0)
        return OutcomeCount(
            count=count,
            pct_of_analyzed=round(count / analyzed, 4) if analyzed else 0.0,
        )

    return OutcomeBreakdown(
        analyzed_count=analyzed,
        coverage_pct=coverage,
        booking=_oc("booking"),
        escalation=_oc("escalation"),
        not_interested=_oc("not_interested"),
        no_output=_oc("no_output"),
        follow_up=_oc("follow_up"),
        other=_oc("other"),
    )


async def _fetch_volume_duration_cost(
    session: AsyncSession, filters: list
) -> dict[str, Any]:
    connected_expr = case((Call.status.in_(CONNECTED), 1), else_=0)
    not_connected_expr = case((Call.status.in_(NOT_CONNECTED), 1), else_=0)
    connected_cost_expr = case((Call.status.in_(CONNECTED), Call.cost), else_=None)
    retry_expr = case((Call.retry_count > 0, 1), else_=0)
    retry_count_expr = case((Call.retry_count > 0, Call.retry_count), else_=None)

    row = (await session.execute(
        select(
            func.count().label("total"),
            func.coalesce(func.sum(connected_expr), 0).label("connected"),
            func.coalesce(func.sum(not_connected_expr), 0).label("not_connected"),
            func.coalesce(func.sum(Call.cost), 0.0).label("total_cost"),
            func.coalesce(func.avg(Call.duration), 0.0).label("avg_duration"),
            func.coalesce(func.sum(Call.duration), 0.0).label("total_duration"),
            func.coalesce(func.avg(connected_cost_expr), 0.0).label("avg_cost_connected"),
            func.coalesce(func.sum(retry_expr), 0).label("calls_with_retry"),
            func.avg(retry_count_expr).label("avg_retries"),
        ).where(*filters)
    )).one()

    # percentile_cont uses a separate query (ordered-set aggregate)
    p50_row = (await session.execute(
        select(
            func.percentile_cont(0.5).within_group(Call.duration.asc()).label("p50"),
            func.percentile_cont(0.9).within_group(Call.duration.asc()).label("p90"),
        ).where(*filters, Call.duration.isnot(None))
    )).one()

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
    session: AsyncSession, filters: list
) -> dict[str, int]:
    rows = await session.execute(
        select(CallAnalysis.outcome, func.count().label("cnt"))
        .join(Call, Call.id == CallAnalysis.call_id)
        .where(*filters)
        .group_by(CallAnalysis.outcome)
    )
    return {row.outcome: row.cnt for row in rows}


async def _fetch_not_connected_breakdown(
    session: AsyncSession, filters: list
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
        outcomes=_outcome_breakdown(outcome_counts, connected),
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
    agg, outcome_counts, nc_breakdown = (
        await _fetch_volume_duration_cost(session, filters),
        await _fetch_outcome_counts(session, filters),
        await _fetch_not_connected_breakdown(session, filters),
    )
    return _build_overview(agg, outcome_counts, nc_breakdown, date_from, date_to)


async def get_by_agent(
    session: AsyncSession,
    client_id: uuid.UUID,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    batch_id: uuid.UUID | None = None,
) -> list[AgentStats]:
    base = _base_filters(client_id, date_from, date_to, None, batch_id)

    agent_rows = await session.execute(
        select(Call.agent_id).where(*base).distinct()
    )
    agent_ids = [r.agent_id for r in agent_rows]

    results: list[AgentStats] = []
    for aid in agent_ids:
        filters = base + [Call.agent_id == aid]
        agg = await _fetch_volume_duration_cost(session, filters)
        outcome_counts = await _fetch_outcome_counts(session, filters)
        connected = agg["connected"]
        avg_per_call = round(agg["total_cost"] / agg["total"], 4) if agg["total"] else 0.0
        results.append(AgentStats(
            agent_id=aid,
            call_volume=_volume_stats(agg["total"], connected, agg["not_connected"]),
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
            outcomes=_outcome_breakdown(outcome_counts, connected),
        ))
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

    batch_rows = await session.execute(
        select(Call.batch_id).where(*base, Call.batch_id.isnot(None)).distinct()
    )
    batch_ids = [r.batch_id for r in batch_rows]

    results: list[BatchStats] = []
    for bid in batch_ids:
        batch = await session.get(Batch, bid)
        if batch is None:
            continue
        filters = base + [Call.batch_id == bid]
        agg = await _fetch_volume_duration_cost(session, filters)
        outcome_counts = await _fetch_outcome_counts(session, filters)
        results.append(BatchStats(
            batch_id=batch.voice_batch_id,
            batch_status=batch.status,
            scheduled_at=batch.scheduled_at,
            total_recipients=batch.total_count,
            call_volume=_volume_stats(agg["total"], agg["connected"], agg["not_connected"]),
            outcomes=_outcome_breakdown(outcome_counts, agg["connected"]),
        ))
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
            outcomes={b: 0 for b in OUTCOME_BUCKETS},
        )

    outcome_rows = await session.execute(
        select(
            func.date_trunc(trunc, Call.created_at).label("bucket"),
            CallAnalysis.outcome,
            func.count().label("cnt"),
        )
        .join(Call, Call.id == CallAnalysis.call_id)
        .where(*filters)
        .group_by(text("bucket"), CallAnalysis.outcome)
        .order_by(text("bucket"))
    )
    for row in outcome_rows:
        date_str = row.bucket.date().isoformat()
        if date_str in points_by_date and row.outcome in OUTCOME_BUCKETS:
            points_by_date[date_str].outcomes[row.outcome] = int(row.cnt)

    return list(points_by_date.values())
