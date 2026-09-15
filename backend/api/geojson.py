"""GeoJSON serialization — the contract between Python and the map."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lib.models import (
    MonitoringSite,
    ParameterSeries,
    RiverSegment,
    SegmentCondition,
    SiteCondition,
    StationRating,
)

#: Rendering hint so MapLibre can widen big rivers without another data join.
STREAM_ORDER_WIDTHS: dict[int, float] = {1: 1.0, 2: 1.5, 3: 2.0, 4: 3.0, 5: 4.5, 6: 6.0, 7: 8.0}


def line_width_for(stream_order: int | None) -> float:
    if stream_order is None:
        return 2.0
    return STREAM_ORDER_WIDTHS.get(min(stream_order, 7), 2.0)


def segment_feature(segment: RiverSegment, condition: SegmentCondition | None) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "comid": segment.comid,
        "name": segment.name,
        "stream_order": segment.stream_order,
        "length_km": segment.length_km,
        "line_width": line_width_for(segment.stream_order),
        "status": "gray",
        "color": "#9aa0a6",
        "assignment": "unassigned",
        "reason": "no condition computed yet",
        "source_site_id": None,
        "distance_km": None,
    }
    if condition is not None:
        properties.update(
            status=condition.status,
            color=condition.color,
            assignment=condition.assignment,
            reason=condition.reason,
            source_site_id=condition.source_site_id,
            distance_km=condition.distance_km,
            computed_at=condition.computed_at.isoformat(),
        )
    return {
        "type": "Feature",
        "id": segment.comid,
        "geometry": {"type": "MultiLineString", "coordinates": segment.geometry},
        "properties": properties,
    }


def velocity_properties(condition: SiteCondition | None) -> dict[str, Any]:
    if condition is None or condition.velocity is None:
        return {
            "velocity_fps": None,
            "velocity_mph": None,
            "velocity_method": None,
            "velocity_confidence": None,
            "velocity_note": None,
            "cross_section_area_sqft": None,
        }
    velocity = condition.velocity
    return {
        "velocity_fps": round(velocity.velocity_fps, 2),
        "velocity_mph": round(velocity.velocity_mph, 2),
        "velocity_method": velocity.method,
        "velocity_confidence": velocity.confidence,
        "velocity_note": velocity.note,
        "cross_section_area_sqft": (
            round(velocity.area_sqft, 1) if velocity.area_sqft is not None else None
        ),
    }


def site_feature(
    site: MonitoringSite,
    condition: SiteCondition | None,
    *,
    rating: StationRating | None = None,
    series: Sequence[ParameterSeries] = (),
) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "site_id": site.site_id,
        "site_number": site.site_number,
        "name": site.name,
        "huc8": site.huc8,
        "drainage_area_sqmi": site.drainage_area_sqmi,
        "comid": site.comid,
        "snap_distance_m": site.snap_distance_m,
        "status": condition.status if condition else "gray",
        "color": condition.color if condition else "#9aa0a6",
        "reason": condition.reason if condition else "no condition computed yet",
        "discharge_cfs": condition.discharge_cfs if condition else None,
        "gage_height_ft": condition.gage_height_ft if condition else None,
        "observed_at": (
            condition.observed_at.isoformat() if condition and condition.observed_at else None
        ),
        "age_minutes": condition.age_minutes if condition else None,
        "percentile": condition.percentile if condition else None,
        "trend": condition.trend if condition else "unknown",
        "activity": condition.activity if condition else None,
        "thresholds": (
            condition.thresholds.model_dump(mode="json")
            if condition and condition.thresholds
            else None
        ),
        "available_parameters": sorted({item.parameter_code for item in series}),
        "rating": rating.model_dump(mode="json") if rating else None,
    }
    properties.update(velocity_properties(condition))
    return {
        "type": "Feature",
        "id": site.site_id,
        "geometry": {"type": "Point", "coordinates": [site.longitude, site.latitude]},
        "properties": properties,
    }


def feature_collection(features: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features, **extra}
