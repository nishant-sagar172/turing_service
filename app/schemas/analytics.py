"""Response schemas for the analytics endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class CallVolumeStats(BaseModel):
    total: int
    connected: int
    not_connected: int
    pending: int
    connection_rate: float


class DurationStats(BaseModel):
    total_seconds: float
    avg_seconds: float
    p50_seconds: float | None
    p90_seconds: float | None


class CostStats(BaseModel):
    total: float
    avg_per_call: float
    avg_per_connected: float


class OutcomeCount(BaseModel):
    count: int
    pct_of_analyzed: float


class OutcomeBreakdown(BaseModel):
    """Two resolutions of the same analysed calls — never sum them together.

    Both maps are keyed by the values actually stored, so registering a new
    workflow outcome needs no schema change. `by_disposition_status` is the
    business rollup of `by_call_outcome`; a key is absent when its count is zero.
    """

    analyzed_count: int
    coverage_pct: float
    by_call_outcome: dict[str, OutcomeCount]
    by_disposition_status: dict[str, OutcomeCount]
    # Temporary backward compatibility: the pre-disposition fixed buckets.
    booking: OutcomeCount
    escalation: OutcomeCount
    not_interested: OutcomeCount
    no_output: OutcomeCount
    follow_up: OutcomeCount
    other: OutcomeCount
    not_reached: OutcomeCount


class RetryStats(BaseModel):
    calls_with_retry: int
    avg_retries: float | None


class AnalyticsPeriod(BaseModel):
    date_from: str | None
    date_to: str | None


class AnalyticsOverview(BaseModel):
    period: AnalyticsPeriod
    call_volume: CallVolumeStats
    duration: DurationStats
    cost: CostStats
    outcomes: OutcomeBreakdown
    not_connected_breakdown: dict[str, int]
    retry_stats: RetryStats


class AgentStats(BaseModel):
    agent_id: str
    call_volume: CallVolumeStats
    duration: DurationStats
    cost: CostStats
    outcomes: OutcomeBreakdown


class BatchStats(BaseModel):
    batch_id: str | None
    batch_status: str
    scheduled_at: str | None
    total_recipients: int
    call_volume: CallVolumeStats
    duration: DurationStats
    cost: CostStats
    outcomes: OutcomeBreakdown


class TimeseriesPoint(BaseModel):
    date: str
    total: int
    connected: int
    not_connected: int
    by_call_outcome: dict[str, int]
    by_disposition_status: dict[str, int]
    outcomes: dict[str, int] = {}
