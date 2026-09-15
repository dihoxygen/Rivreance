"""Small geodesy helpers for the gage-to-flowline spatial join.

The MVP deliberately avoids GeoPandas/Shapely: one basin holds a few thousand
flowlines and a few dozen gages, so a local equirectangular projection plus
point-to-segment distance is fast enough and keeps the install light. PostGIS
does the same work server-side once data lands in Supabase.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_008.8

Coordinate = Sequence[float]
LineCoordinates = Sequence[Coordinate]
MultiLineCoordinates = Sequence[LineCoordinates]


@dataclass(frozen=True, slots=True)
class Bbox:
    """WGS84 bounding box in OGC order (west, south, east, north)."""

    west: float
    south: float
    east: float
    north: float

    def as_param(self) -> str:
        return f"{self.west},{self.south},{self.east},{self.north}"

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.west, self.south, self.east, self.north)

    def contains(self, lon: float, lat: float) -> bool:
        return self.west <= lon <= self.east and self.south <= lat <= self.north

    def expanded(self, meters: float) -> Bbox:
        lat_pad = meters / 111_320.0
        mid_lat = math.radians((self.south + self.north) / 2)
        lon_pad = meters / max(111_320.0 * math.cos(mid_lat), 1.0)
        return Bbox(
            self.west - lon_pad, self.south - lat_pad, self.east + lon_pad, self.north + lat_pad
        )

    @classmethod
    def from_coordinates(cls, coordinates: Iterable[Coordinate]) -> Bbox:
        lons: list[float] = []
        lats: list[float] = []
        for lon, lat, *_rest in coordinates:
            lons.append(lon)
            lats.append(lat)
        if not lons:
            raise ValueError("cannot build a bbox from zero coordinates")
        return cls(min(lons), min(lats), max(lons), max(lats))


def flatten_coordinates(geometry: object) -> list[tuple[float, float]]:
    """Flatten arbitrarily nested GeoJSON coordinate arrays into (lon, lat) pairs."""
    if isinstance(geometry, dict):
        return flatten_coordinates(geometry.get("coordinates", []))
    points: list[tuple[float, float]] = []
    stack: list[object] = [geometry]
    while stack:
        node = stack.pop()
        if (
            isinstance(node, Sequence)
            and len(node) >= 2
            and all(isinstance(value, (int, float)) for value in node[:2])
        ):
            points.append((float(node[0]), float(node[1])))
        elif isinstance(node, Sequence):
            stack.extend(node)
    return points


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _local_meters(lon: float, lat: float, ref_lon: float, ref_lat: float) -> tuple[float, float]:
    """Project to meters relative to a reference point (fine over a single basin)."""
    lat_scale = math.pi * EARTH_RADIUS_M / 180.0
    return (
        (lon - ref_lon) * lat_scale * math.cos(math.radians(ref_lat)),
        (lat - ref_lat) * lat_scale,
    )


def point_to_segment_distance_m(
    lon: float, lat: float, start: Coordinate, end: Coordinate
) -> float:
    """Distance from a point to a single line segment."""
    px, py = _local_meters(lon, lat, lon, lat)
    ax, ay = _local_meters(start[0], start[1], lon, lat)
    bx, by = _local_meters(end[0], end[1], lon, lat)
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def distance_to_multiline_m(lon: float, lat: float, coordinates: MultiLineCoordinates) -> float:
    """Shortest distance from a point to any part of a (Multi)LineString."""
    best = math.inf
    for line in coordinates:
        for start, end in zip(line, line[1:], strict=False):
            best = min(best, point_to_segment_distance_m(lon, lat, start, end))
        if len(line) == 1:
            best = min(best, haversine_m(lon, lat, line[0][0], line[0][1]))
    return best


def bbox_of_multiline(coordinates: MultiLineCoordinates) -> Bbox:
    return Bbox.from_coordinates(point for line in coordinates for point in line)
