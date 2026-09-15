from __future__ import annotations

import pytest

from lib.geo import (
    Bbox,
    distance_to_multiline_m,
    flatten_coordinates,
    haversine_m,
    point_to_segment_distance_m,
)


def test_haversine_matches_known_degree_of_latitude():
    # One degree of latitude is ~111.2 km anywhere on the globe.
    assert haversine_m(-87.0, 33.0, -87.0, 34.0) == pytest.approx(111_195, rel=0.01)


def test_point_to_segment_distance_clamps_to_endpoints():
    start, end = (-87.0, 33.0), (-87.0, 33.01)
    # Beyond the northern endpoint: distance is measured to that endpoint.
    beyond = point_to_segment_distance_m(-87.0, 33.02, start, end)
    assert beyond == pytest.approx(haversine_m(-87.0, 33.02, -87.0, 33.01), rel=0.01)


def test_point_to_segment_distance_projects_perpendicular():
    start, end = (-87.0, 33.0), (-87.0, 33.02)
    distance = point_to_segment_distance_m(-86.999, 33.01, start, end)
    assert distance == pytest.approx(haversine_m(-86.999, 33.01, -87.0, 33.01), rel=0.01)


def test_distance_to_multiline_takes_the_closest_part():
    lines = [
        [[-87.0, 33.0], [-87.0, 33.02]],
        [[-86.5, 33.0], [-86.5, 33.02]],
    ]
    assert distance_to_multiline_m(-86.99, 33.01, lines) < 1_000
    assert distance_to_multiline_m(-86.51, 33.01, lines) < 1_000


def test_bbox_expansion_grows_in_both_axes():
    bbox = Bbox(-87.0, 33.0, -86.9, 33.1)
    expanded = bbox.expanded(1_000)
    assert expanded.west < bbox.west and expanded.east > bbox.east
    assert expanded.south < bbox.south and expanded.north > bbox.north
    assert bbox.contains(-86.95, 33.05)
    assert not bbox.contains(-88.0, 33.05)


def test_bbox_from_coordinates_and_param_format():
    bbox = Bbox.from_coordinates([(-87.5, 33.1), (-86.9, 33.8), (-87.2, 33.4)])
    assert bbox.as_tuple() == (-87.5, 33.1, -86.9, 33.8)
    assert bbox.as_param() == "-87.5,33.1,-86.9,33.8"


def test_flatten_coordinates_handles_nested_geojson():
    geometry = {"type": "MultiLineString", "coordinates": [[[1.0, 2.0], [3.0, 4.0]]]}
    assert sorted(flatten_coordinates(geometry)) == [(1.0, 2.0), (3.0, 4.0)]
