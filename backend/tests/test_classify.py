from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from lib.classify import (
    build_stats,
    classify_value,
    detect_trend,
    is_stale,
    percentile_from_stats,
    percentile_rank,
    quantile,
    resolve_thresholds,
    thresholds_from_stats,
    worst_status,
)
from lib.models import ActivityThresholds, ParameterSeries, SeriesPoint

KAYAK = ActivityThresholds(
    activity="kayaking", min_cfs=60, opt_min_cfs=120, opt_max_cfs=800, max_cfs=1500
)


@pytest.mark.parametrize(
    ("discharge", "expected"),
    [
        (30, "red"),      # below runnable minimum
        (60, "yellow"),   # exactly at the minimum
        (119, "yellow"),
        (120, "green"),   # bottom of the optimal window
        (400, "green"),
        (800, "green"),   # top of the optimal window
        (801, "yellow"),
        (1500, "yellow"), # exactly at the safe maximum
        (1501, "red"),    # over the safe maximum
    ],
)
def test_classify_value_covers_every_band_boundary(discharge, expected):
    status, reason = classify_value(discharge, KAYAK)
    assert status == expected
    assert str(discharge) in reason or f"{discharge:g}" in reason


def test_quantile_interpolates_like_numpy_linear():
    values = [1, 2, 3, 4]
    assert quantile(values, 0.0) == 1
    assert quantile(values, 0.5) == pytest.approx(2.5)
    assert quantile(values, 0.25) == pytest.approx(1.75)
    assert quantile(values, 1.0) == 4


def test_build_stats_needs_a_minimum_record():
    assert build_stats([1, 2, 3, 4], parameter_code="00060", window_days=30) is None

    stats = build_stats(list(range(1, 101)), parameter_code="00060", window_days=30)
    assert stats is not None
    assert stats.count == 100
    assert stats.p50 == pytest.approx(50.5)
    assert stats.p05 < stats.p25 < stats.p50 < stats.p75 < stats.p95


def test_percentile_rank_is_share_at_or_below():
    assert percentile_rank(3, [1, 2, 3, 4]) == pytest.approx(75.0)
    assert percentile_rank(0, [1, 2, 3, 4]) == pytest.approx(0.0)
    assert percentile_rank(1, []) is None


def test_percentile_from_stats_interpolates_between_anchors():
    stats = build_stats(list(range(1, 101)), parameter_code="00060", window_days=30)
    assert stats is not None

    assert percentile_from_stats(stats.p50, stats) == pytest.approx(50.0)
    assert percentile_from_stats(stats.p75, stats) == pytest.approx(75.0)
    midpoint = (stats.p50 + stats.p75) / 2
    assert percentile_from_stats(midpoint, stats) == pytest.approx(62.5, abs=0.6)


def test_percentile_from_stats_clamps_both_tails():
    stats = build_stats(list(range(1, 101)), parameter_code="00060", window_days=30)
    assert stats is not None
    assert percentile_from_stats(-5.0, stats) == 5.0
    assert percentile_from_stats(10_000.0, stats) == 95.0


def test_derived_thresholds_are_activity_specific():
    stats = build_stats(list(range(1, 101)), parameter_code="00060", window_days=30)
    assert stats is not None

    kayaking = thresholds_from_stats(stats, "kayaking")
    fishing = thresholds_from_stats(stats, "fishing")

    assert kayaking.source == "derived_percentile"
    # Paddlers want more water than anglers, so every band sits higher.
    assert kayaking.min_cfs > fishing.min_cfs
    assert kayaking.opt_min_cfs > fishing.opt_min_cfs
    assert kayaking.opt_max_cfs > fishing.opt_max_cfs
    assert kayaking.max_cfs > fishing.max_cfs


def test_resolve_thresholds_prefers_curated_over_derived():
    stats = build_stats(list(range(1, 101)), parameter_code="00060", window_days=30)
    assert resolve_thresholds(activity="kayaking", curated=KAYAK, stats=stats) is KAYAK
    assert resolve_thresholds(activity="kayaking", curated=None, stats=stats) is not None
    assert resolve_thresholds(activity="kayaking", curated=None, stats=None) is None


def test_staleness_uses_the_configured_window():
    now = datetime(2026, 9, 14, 12, tzinfo=UTC)
    assert is_stale(None, now, 120) is True
    assert is_stale(now - timedelta(minutes=30), now, 120) is False
    assert is_stale(now - timedelta(minutes=121), now, 120) is True


def test_worst_status_wins_for_aggregation():
    assert worst_status(["green", "yellow", "red"]) == "red"
    assert worst_status(["green", "gray"]) == "green"
    assert worst_status([]) == "gray"


def _series(values: list[float]) -> ParameterSeries:
    start = datetime(2026, 9, 14, 6, tzinfo=UTC)
    return ParameterSeries(
        parameter_code="00065",
        unit="ft",
        points=tuple(
            SeriesPoint(time=start + timedelta(hours=index), value=value)
            for index, value in enumerate(values)
        ),
    )


def test_detect_trend_labels_rising_falling_and_steady():
    assert detect_trend(_series([1.0, 1.1, 1.3, 1.6])) == "rising"
    assert detect_trend(_series([2.0, 1.8, 1.5, 1.2])) == "falling"
    assert detect_trend(_series([2.0, 2.0, 2.01, 2.0])) == "steady"
    assert detect_trend(None) == "unknown"
    assert detect_trend(_series([1.0])) == "unknown"
