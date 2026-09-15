"""Turn raw readings into a traffic-light condition for an activity.

Two rules, in priority order:

1. **Curated activity thresholds** (`config/activity_thresholds.json`) — flow windows
   a paddler or angler cares about::

       red    Q < min_cfs            or Q > max_cfs
       yellow min_cfs <= Q < opt_min or opt_max < Q <= max_cfs
       green  opt_min <= Q <= opt_max

2. **Percentile fallback** — when a station has no curated window, thresholds are
   derived from its own recent daily-values record, shifted per activity (paddlers
   want more water than anglers).

Anything stale or unreadable is gray, never green.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal

from lib.config import Activity
from lib.models import (
    STATUS_COLORS,
    ActivityThresholds,
    ParameterSeries,
    ParameterStats,
    Status,
)

STATUS_SEVERITY: dict[Status, int] = {"gray": 0, "green": 1, "yellow": 2, "red": 3}

#: Percentile anchors used to derive provisional thresholds per activity.
#: (min, opt_min, opt_max, max) as attribute names on `ParameterStats`.
ACTIVITY_PERCENTILE_ANCHORS: dict[Activity, tuple[str, str, str, str]] = {
    "kayaking": ("p25", "p50", "p90", "p95"),
    "fishing": ("p05", "p10", "p75", "p90"),
}

TREND_LOOKBACK_HOURS = 3.0
TREND_MIN_CHANGE_FRACTION = 0.05


def quantile(values: Sequence[float], fraction: float) -> float:
    """Linear-interpolation quantile (matches numpy's default `linear` method)."""
    if not values:
        raise ValueError("quantile of an empty sequence")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * min(max(fraction, 0.0), 1.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def build_stats(
    values: Sequence[float],
    *,
    parameter_code: str,
    window_days: int,
    source: Literal["daily", "continuous"] = "daily",
) -> ParameterStats | None:
    usable = [value for value in values if math.isfinite(value)]
    if len(usable) < 5:
        return None
    return ParameterStats(
        parameter_code=parameter_code,
        window_days=window_days,
        count=len(usable),
        source=source,
        p05=quantile(usable, 0.05),
        p10=quantile(usable, 0.10),
        p25=quantile(usable, 0.25),
        p50=quantile(usable, 0.50),
        p75=quantile(usable, 0.75),
        p90=quantile(usable, 0.90),
        p95=quantile(usable, 0.95),
    )


def percentile_rank(value: float, values: Sequence[float]) -> float | None:
    """Share of the record at or below `value`, as a 0–100 percentile."""
    usable = [item for item in values if math.isfinite(item)]
    if not usable:
        return None
    at_or_below = sum(1 for item in usable if item <= value)
    return round(100.0 * at_or_below / len(usable), 1)


#: Percentiles stored on `ParameterStats`, in order.
STATS_ANCHORS: tuple[tuple[float, str], ...] = (
    (5.0, "p05"),
    (10.0, "p10"),
    (25.0, "p25"),
    (50.0, "p50"),
    (75.0, "p75"),
    (90.0, "p90"),
    (95.0, "p95"),
)


def percentile_from_stats(value: float, stats: ParameterStats) -> float:
    """Interpolate a percentile from the stored anchors.

    Only seven quantiles are kept per station, so the result is piecewise linear
    between them and clamped to 5–95: a reading beyond either tail reports as "at
    least as extreme as the 5th/95th percentile" rather than inventing precision.
    """
    points = [(percentile, getattr(stats, attribute)) for percentile, attribute in STATS_ANCHORS]
    if value <= points[0][1]:
        return points[0][0]
    for (low_pct, low_value), (high_pct, high_value) in zip(points, points[1:], strict=False):
        if value <= high_value:
            if high_value <= low_value:
                return high_pct
            fraction = (value - low_value) / (high_value - low_value)
            return round(low_pct + fraction * (high_pct - low_pct), 1)
    return points[-1][0]


def thresholds_from_stats(stats: ParameterStats, activity: Activity) -> ActivityThresholds:
    """Derive a provisional flow window from a station's own record."""
    min_key, opt_min_key, opt_max_key, max_key = ACTIVITY_PERCENTILE_ANCHORS[activity]
    return ActivityThresholds(
        activity=activity,
        parameter_code=stats.parameter_code,
        min_cfs=getattr(stats, min_key),
        opt_min_cfs=getattr(stats, opt_min_key),
        opt_max_cfs=getattr(stats, opt_max_key),
        max_cfs=getattr(stats, max_key),
        source="derived_percentile",
        note=(
            f"Derived from {stats.count} {stats.source} values over {stats.window_days} days "
            f"({min_key}/{opt_min_key}/{opt_max_key}/{max_key}); not a safety rating"
        ),
    )


def classify_value(value: float, thresholds: ActivityThresholds) -> tuple[Status, str]:
    """Apply the traffic-light rule for one flow value."""
    if value < thresholds.min_cfs:
        return "red", f"{value:g} is below the runnable minimum of {thresholds.min_cfs:g}"
    if value > thresholds.max_cfs:
        return "red", f"{value:g} exceeds the safe maximum of {thresholds.max_cfs:g}"
    if value < thresholds.opt_min_cfs:
        return "yellow", f"{value:g} is below the optimal range ({thresholds.opt_min_cfs:g}+)"
    if value > thresholds.opt_max_cfs:
        return "yellow", f"{value:g} is above the optimal range (up to {thresholds.opt_max_cfs:g})"
    return (
        "green",
        f"{value:g} is inside the optimal range "
        f"{thresholds.opt_min_cfs:g}–{thresholds.opt_max_cfs:g}",
    )


def resolve_thresholds(
    *,
    activity: Activity,
    curated: ActivityThresholds | None,
    stats: ParameterStats | None,
) -> ActivityThresholds | None:
    if curated is not None:
        return curated
    if stats is not None:
        return thresholds_from_stats(stats, activity)
    return None


def is_stale(observed_at: datetime | None, now: datetime, stale_after_minutes: int) -> bool:
    if observed_at is None:
        return True
    return (now - observed_at) > timedelta(minutes=stale_after_minutes)


def age_minutes(observed_at: datetime | None, now: datetime) -> float | None:
    if observed_at is None:
        return None
    return round((now - observed_at).total_seconds() / 60.0, 1)


def color_for(status: Status) -> str:
    return STATUS_COLORS[status]


def worst_status(statuses: Sequence[Status]) -> Status:
    if not statuses:
        return "gray"
    return max(statuses, key=lambda status: STATUS_SEVERITY[status])


def detect_trend(series: ParameterSeries | None) -> str:
    """Compare the newest reading with one ~3 h earlier to label the stage trend."""
    if series is None or len(series.points) < 3:
        return "unknown"
    points = sorted(series.points, key=lambda point: point.time)
    latest = points[-1]
    cutoff = latest.time - timedelta(hours=TREND_LOOKBACK_HOURS)
    earlier = next((point for point in points if point.time >= cutoff), points[0])
    if earlier is latest or earlier.value == 0:
        return "steady"
    change = (latest.value - earlier.value) / abs(earlier.value)
    if change > TREND_MIN_CHANGE_FRACTION:
        return "rising"
    if change < -TREND_MIN_CHANGE_FRACTION:
        return "falling"
    return "steady"
