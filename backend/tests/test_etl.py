"""Tests for the ETL parsing and filtering steps, using USGS-shaped fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from conftest import make_segment, make_site

from etl.ingest_flowlines import flowline_to_segment, in_basin
from etl.ingest_observations import parse_daily_values, parse_readings, parse_series
from etl.ingest_sites import active_site_ids, parse_site, snap_sites_to_segments

NOW = datetime(2026, 9, 14, 12, tzinfo=UTC)


def _site_feature(site_id: str = "USGS-02462000", **overrides) -> dict:
    properties = {
        "id": site_id,
        "monitoring_location_number": site_id.split("-")[-1],
        "monitoring_location_name": "VALLEY CREEK NEAR OAK GROVE AL",
        "hydrologic_unit_code": "031601120303",
        "site_type": "Stream",
        "drainage_area": 140.0,
    }
    properties.update(overrides)
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [-87.05, 33.35]},
    }


def test_parse_site_normalizes_the_shouty_usgs_name():
    site = parse_site(_site_feature(), "03160112")
    assert site is not None
    assert site.name == "Valley Creek Near Oak Grove Al"
    assert site.site_number == "02462000"
    assert (site.longitude, site.latitude) == (-87.05, 33.35)
    assert site.drainage_area_sqmi == pytest.approx(140.0)


def test_parse_site_rejects_features_without_coordinates():
    broken = _site_feature()
    broken["geometry"] = {"type": "Point", "coordinates": []}
    assert parse_site(broken, "03160112") is None


def _latest_feature(site_id: str, time: datetime, parameter_code: str = "00060") -> dict:
    return {
        "properties": {
            "monitoring_location_id": site_id,
            "parameter_code": parameter_code,
            "value": "81.7",
            "unit_of_measure": "ft^3/s",
            "time": time.isoformat(),
            "approval_status": "Provisional",
        }
    }


def test_active_site_ids_drops_retired_time_series():
    features = [
        _latest_feature("USGS-live", NOW - timedelta(minutes=15)),
        _latest_feature("USGS-retired", datetime(2003, 10, 1, tzinfo=UTC)),
    ]
    assert active_site_ids(features, now=NOW, inactive_after_days=30) == {"USGS-live"}


def test_parse_readings_keeps_only_the_newest_value_per_parameter():
    features = [
        _latest_feature("USGS-1", NOW - timedelta(hours=2)),
        _latest_feature("USGS-1", NOW),
        _latest_feature("USGS-1", NOW - timedelta(minutes=5), parameter_code="00065"),
    ]

    readings = parse_readings(features)

    assert [reading.parameter_code for reading in readings["USGS-1"]] == ["00060", "00065"]
    discharge = next(r for r in readings["USGS-1"] if r.parameter_code == "00060")
    assert discharge.observed_at == NOW


def test_parse_readings_skips_unparseable_values():
    broken = _latest_feature("USGS-1", NOW)
    broken["properties"]["value"] = "Ice"
    assert parse_readings([broken]) == {}


def test_parse_series_sorts_ascending_by_time():
    features = [
        {"properties": {"time": (NOW - timedelta(hours=hours)).isoformat(), "value": str(hours),
                        "unit_of_measure": "ft^3/s"}}
        for hours in (0, 3, 1, 2)
    ]

    series = parse_series(features, parameter_code="00060")

    assert series is not None
    assert [point.value for point in series.points] == [3.0, 2.0, 1.0, 0.0]
    assert series.unit == "ft^3/s"


def test_parse_series_returns_none_when_empty():
    assert parse_series([], parameter_code="00060") is None


def test_parse_daily_values_accepts_date_only_timestamps():
    features = [
        {"properties": {"time": "2026-09-13", "value": "11.4"}},
        {"properties": {"time": "2026-09-12", "value": None}},
    ]
    assert parse_daily_values(features) == [11.4]


def _flowline_feature(**overrides) -> dict:
    properties = {
        "comid": 18226803,
        "reachcode": "03160112000597",
        "gnis_name": " ",
        "streamorde": 4.0,
        "lengthkm": 0.069,
        "slope": 0.0181,
        "levelpathi": 290048945.0,
        "pathlength": 619.755,
        "totdasqkm": 2.49,
        "qe_ma": 1.859,
        "ve_ma": 0.807,
    }
    properties.update(overrides)
    return {
        "properties": properties,
        "geometry": {"type": "MultiLineString", "coordinates": [[[-87.0, 33.0], [-87.01, 33.01]]]},
    }


def test_flowline_to_segment_maps_nhdplus_attributes():
    segment = flowline_to_segment(_flowline_feature(), "03160112")

    assert segment is not None
    assert segment.comid == 18226803
    assert segment.name is None  # blank GNIS names become None
    assert segment.stream_order == 4
    assert segment.erom_velocity_fps == pytest.approx(0.807)
    assert segment.geometry == [[[-87.0, 33.0], [-87.01, 33.01]]]


def test_flowline_to_segment_promotes_a_plain_linestring():
    feature = _flowline_feature()
    feature["geometry"] = {"type": "LineString", "coordinates": [[-87.0, 33.0], [-87.01, 33.01]]}
    segment = flowline_to_segment(feature, "03160112")
    assert segment is not None
    assert segment.geometry == [[[-87.0, 33.0], [-87.01, 33.01]]]


def test_flowline_to_segment_rejects_degenerate_geometry():
    feature = _flowline_feature()
    feature["geometry"] = {"type": "MultiLineString", "coordinates": [[[-87.0, 33.0]]]}
    assert flowline_to_segment(feature, "03160112") is None


def test_in_basin_uses_the_reach_code_prefix():
    inside = flowline_to_segment(_flowline_feature(), "03160112")
    outside = flowline_to_segment(_flowline_feature(reachcode="03160113000940"), "03160112")
    assert inside is not None and outside is not None
    assert in_basin(inside, "03160112") is True
    assert in_basin(outside, "03160112") is False


def test_snapping_picks_the_closest_flowline_and_copies_its_mainstem_attributes():
    site = make_site(comid=None, levelpath_id=None, path_length_km=None, segment_drainage_sqkm=None)
    near = make_segment(comid=1, coordinates=[[[-87.0501, 33.3499], [-87.0499, 33.3501]]])
    far = make_segment(comid=2, coordinates=[[[-86.0, 33.0], [-86.01, 33.01]]])

    snap_sites_to_segments([site], [far, near], max_distance_m=750)

    assert site.comid == 1
    assert site.levelpath_id == near.levelpath_id
    assert site.path_length_km == near.path_length_km
    assert site.snap_distance_m is not None and site.snap_distance_m < 50


def test_snapping_leaves_distant_sites_unmatched():
    site = make_site(comid=None)
    far = make_segment(comid=2, coordinates=[[[-86.0, 33.0], [-86.01, 33.01]]])

    snap_sites_to_segments([site], [far], max_distance_m=750)

    assert site.comid is None
    assert site.snap_distance_m is None
