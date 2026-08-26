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
    analyzed_count: int
    coverage_pct: float
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
    outcomes: dict[str, int]
