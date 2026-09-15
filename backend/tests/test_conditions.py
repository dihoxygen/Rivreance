from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import make_reading, make_segment, make_site

from lib.conditions import (
    GageAnchor,
    assign_segment_conditions,
    build_site_condition,
    latest_reading,
)
from lib.models import ParameterSeries, SeriesPoint, StationRating
from lib.rating import fit_power_law


def _condition(settings, now, **kwargs):
    defaults = {
        "site": make_site(),
        "activity": "kayaking",
        "readings": [make_reading("00060", 200.0, observed_at=now)],
        "settings": settings,
        "now": now,
    }
    return build_site_condition(**{**defaults, **kwargs})


def test_curated_thresholds_drive_the_status(settings, now):
    # Valley Creek near Oak Grove has a curated kayaking window of 120-800 cfs.
    condition = _condition(settings, now)
    assert condition.status == "green"
    assert condition.thresholds is not None
    assert condition.thresholds.source == "curated"
    assert "optimal range" in condition.reason


def test_flow_below_the_curated_minimum_is_red(settings, now):
    condition = _condition(settings, now, readings=[make_reading("00060", 5.0, observed_at=now)])
    assert condition.status == "red"
    assert "below the runnable minimum" in condition.reason


def test_activity_toggle_changes_the_status_for_the_same_flow(settings, now):
    readings = [make_reading("00060", 50.0, observed_at=now)]
    kayaking = _condition(settings, now, activity="kayaking", readings=readings)
    fishing = _condition(settings, now, activity="fishing", readings=readings)

    # 50 cfs is too low to paddle but inside the angling window.
    assert kayaking.status == "red"
    assert fishing.status == "green"


def test_stale_readings_are_gray_not_green(settings, now):
    stale = now - timedelta(minutes=settings.stale_after_minutes + 5)
    condition = _condition(
        settings, now, readings=[make_reading("00060", 200.0, observed_at=stale)]
    )

    assert condition.status == "gray"
    assert "stale" in condition.reason
    assert condition.age_minutes == pytest.approx(settings.stale_after_minutes + 5, abs=0.1)


def test_stage_only_gages_are_gray(settings, now):
    condition = _condition(
        settings, now, readings=[make_reading("00065", 186.4, observed_at=now, unit="ft")]
    )
    assert condition.status == "gray"
    assert "stage only" in condition.reason
    assert condition.gage_height_ft == pytest.approx(186.4)


def test_missing_thresholds_and_history_leave_the_gage_gray(settings, now):
    condition = _condition(settings, now, site=make_site("USGS-99999999"))
    assert condition.status == "gray"
    assert "no activity thresholds" in condition.reason


def test_velocity_estimate_is_attached_from_the_station_rating(settings, now):
    rating = StationRating(
        site_id="USGS-02462000",
        velocity_rating=fit_power_law([(20, 0.8), (60, 1.1), (120, 1.4), (300, 1.9)]),
        measurement_count=4,
    )
    condition = _condition(settings, now, rating=rating)

    assert condition.velocity is not None
    assert condition.velocity.method == "field_rating"
    assert 0.5 < condition.velocity.velocity_fps < 5.0
    assert condition.velocity.velocity_mph == pytest.approx(
        condition.velocity.velocity_fps * 3600 / 5280
    )


def test_velocity_falls_back_to_the_reach_estimate_when_no_rating(settings, now):
    condition = _condition(settings, now, site=make_site("USGS-02465493"), segment=make_segment())
    assert condition.velocity is not None
    assert condition.velocity.method == "nhdplus_erom"
    assert condition.velocity.confidence == "low"


def test_trend_comes_from_the_cached_series(settings, now):
    series = ParameterSeries(
        parameter_code="00065",
        unit="ft",
        points=tuple(
            SeriesPoint(time=now - timedelta(hours=hours), value=value)
            for hours, value in ((6, 1.0), (4, 1.2), (2, 1.5), (0, 1.9))
        ),
    )
    condition = _condition(settings, now, series=[series])
    assert condition.trend == "rising"


def test_latest_reading_picks_the_newest_observation(now):
    older = make_reading("00060", 100.0, observed_at=now - timedelta(hours=2))
    newer = make_reading("00060", 150.0, observed_at=now)
    assert latest_reading([older, newer], "00060") is newer
    assert latest_reading([older, newer], "00065") is None


def _anchor(settings, now, status_flow: float = 200.0, **site_kwargs) -> GageAnchor:
    site = make_site(**site_kwargs)
    condition = build_site_condition(
        site=site,
        activity="kayaking",
        readings=[make_reading("00060", status_flow, observed_at=now)],
        settings=settings,
        now=now,
    )
    return GageAnchor(site=site, condition=condition)


def test_mainstem_segments_inherit_the_gage_status(settings, now):
    anchor = _anchor(settings, now)
    segment = make_segment(path_length_km=615.0)  # 5 km along the same level path

    conditions = assign_segment_conditions(
        huc8="03160112",
        activity="kayaking",
        segments=[segment],
        anchors=[anchor],
        settings=settings,
        now=now,
    )

    assert len(conditions) == 1
    assert conditions[0].status == "green"
    assert conditions[0].assignment == "mainstem"
    assert conditions[0].distance_km == pytest.approx(5.0)
    assert conditions[0].source_site_id == anchor.site.site_id


def test_far_upstream_segments_on_the_same_path_are_not_colored(settings, now):
    anchor = _anchor(settings, now)
    far = make_segment(
        comid=1, path_length_km=620.0 + settings.mainstem_assign_distance_km + 10,
        coordinates=[[[-80.0, 30.0], [-80.01, 30.01]]],
    )

    conditions = assign_segment_conditions(
        huc8="03160112",
        activity="kayaking",
        segments=[far],
        anchors=[anchor],
        settings=settings,
        now=now,
    )
    assert conditions[0].status == "gray"
    assert conditions[0].assignment == "unassigned"


def test_drainage_mismatch_blocks_mainstem_propagation(settings, now):
    anchor = _anchor(settings, now, segment_drainage_sqkm=10.0)
    big_river = make_segment(drainage_sqkm=5_000.0, coordinates=[[[-80.0, 30.0], [-80.01, 30.01]]])

    conditions = assign_segment_conditions(
        huc8="03160112",
        activity="kayaking",
        segments=[big_river],
        anchors=[anchor],
        settings=settings,
        now=now,
    )
    assert conditions[0].status == "gray"


def test_nearby_segments_on_another_path_fall_back_to_proximity(settings, now):
    anchor = _anchor(settings, now)
    neighbour = make_segment(
        comid=2, levelpath_id=999.0, path_length_km=100.0,
        coordinates=[[[-87.051, 33.351], [-87.049, 33.353]]],
    )

    conditions = assign_segment_conditions(
        huc8="03160112",
        activity="kayaking",
        segments=[neighbour],
        anchors=[anchor],
        settings=settings,
        now=now,
    )
    assert conditions[0].assignment == "proximity"
    assert conditions[0].status == "green"
    assert conditions[0].distance_km is not None and conditions[0].distance_km < 1.0


def test_gray_gages_never_color_a_segment(settings, now):
    stale = now - timedelta(hours=5)
    anchor = GageAnchor(
        site=make_site(),
        condition=build_site_condition(
            site=make_site(),
            activity="kayaking",
            readings=[make_reading("00060", 200.0, observed_at=stale)],
            settings=settings,
            now=now,
        ),
    )
    conditions = assign_segment_conditions(
        huc8="03160112",
        activity="kayaking",
        segments=[make_segment()],
        anchors=[anchor],
        settings=settings,
        now=now,
    )
    assert conditions[0].status == "gray"
    assert conditions[0].source_site_id is None
