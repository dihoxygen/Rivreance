"""Build site and segment conditions from stored observations.

Gages are points; a traffic-style map needs lines. Without hydrologic routing the
MVP propagates each gage's status in two tiers:

1. **Mainstem** — segments sharing the gage's NHDPlus level path, within a capped
   along-path distance and a comparable drainage area. This colors the river a gage
   actually measures, not just the 200 m next to the sensor.
2. **Proximity** — otherwise, the nearest gage within a few kilometers.

Everything else stays gray. Both tiers are recorded in `SegmentCondition.assignment`
so the UI can be honest about how a color was derived.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from lib.classify import (
    age_minutes,
    classify_value,
    color_for,
    detect_trend,
    is_stale,
    percentile_from_stats,
    resolve_thresholds,
)
from lib.config import DISCHARGE_PARAMETER, GAGE_HEIGHT_PARAMETER, Activity, Settings
from lib.geo import bbox_of_multiline, distance_to_multiline_m
from lib.models import (
    MonitoringSite,
    ParameterSeries,
    ParameterStats,
    Reading,
    RiverSegment,
    SegmentCondition,
    SiteCondition,
    StationRating,
)
from lib.thresholds import cross_section_for, thresholds_for
from lib.velocity import estimate_velocity

logger = logging.getLogger(__name__)

#: A segment is only colored from a mainstem gage whose drainage area is within
#: this factor of the segment's, so a headwater reading never colors a big river.
DRAINAGE_RATIO_LIMIT = 4.0


def latest_reading(readings: Sequence[Reading], parameter_code: str) -> Reading | None:
    matching = [reading for reading in readings if reading.parameter_code == parameter_code]
    if not matching:
        return None
    return max(matching, key=lambda reading: reading.observed_at)


def find_series(
    series: Sequence[ParameterSeries], parameter_code: str
) -> ParameterSeries | None:
    return next((item for item in series if item.parameter_code == parameter_code), None)


def find_stats(stats: Sequence[ParameterStats], parameter_code: str) -> ParameterStats | None:
    return next((item for item in stats if item.parameter_code == parameter_code), None)


def build_site_condition(
    *,
    site: MonitoringSite,
    activity: Activity,
    readings: Sequence[Reading],
    series: Sequence[ParameterSeries] = (),
    stats: Sequence[ParameterStats] = (),
    rating: StationRating | None = None,
    segment: RiverSegment | None = None,
    settings: Settings,
    now: datetime,
) -> SiteCondition:
    """Classify one gage for one activity and attach a velocity estimate."""
    discharge = latest_reading(readings, DISCHARGE_PARAMETER)
    gage_height = latest_reading(readings, GAGE_HEIGHT_PARAMETER)
    primary = discharge or gage_height

    velocity = estimate_velocity(
        discharge_cfs=discharge.value if discharge else None,
        gage_height_ft=gage_height.value if gage_height else None,
        velocity_rating=rating.velocity_rating if rating else None,
        area_rating=rating.area_rating if rating else None,
        cross_section=cross_section_for(site.site_id),
        erom_flow_cfs=segment.erom_flow_cfs if segment else None,
        erom_velocity_fps=segment.erom_velocity_fps if segment else None,
    )
    trend = detect_trend(
        find_series(series, GAGE_HEIGHT_PARAMETER) or find_series(series, DISCHARGE_PARAMETER)
    )
    base = {
        "site_id": site.site_id,
        "activity": activity,
        "discharge_cfs": discharge.value if discharge else None,
        "gage_height_ft": gage_height.value if gage_height else None,
        "observed_at": primary.observed_at if primary else None,
        "age_minutes": age_minutes(primary.observed_at if primary else None, now),
        "velocity": velocity,
        "trend": trend,
    }

    if primary is None:
        return SiteCondition(
            status="gray", color=color_for("gray"), reason="no recent reading", **base
        )
    if is_stale(primary.observed_at, now, settings.stale_after_minutes):
        return SiteCondition(
            status="gray",
            color=color_for("gray"),
            reason=(
                f"last reading is {age_minutes(primary.observed_at, now):.0f} minutes old "
                f"(stale after {settings.stale_after_minutes})"
            ),
            metric_parameter=primary.parameter_code,
            metric_value=primary.value,
            unit=primary.unit,
            **base,
        )
    if discharge is None:
        # Pool-stage gages (locks and dams) report only gage height; without a rating
        # curve their stage cannot be mapped onto an activity flow window.
        return SiteCondition(
            status="gray",
            color=color_for("gray"),
            reason="gage reports stage only; no discharge to classify",
            metric_parameter=primary.parameter_code,
            metric_value=primary.value,
            unit=primary.unit,
            **base,
        )

    discharge_stats = find_stats(stats, DISCHARGE_PARAMETER)
    thresholds = resolve_thresholds(
        activity=activity,
        curated=thresholds_for(site.site_id, activity),
        stats=discharge_stats,
    )
    if thresholds is None:
        return SiteCondition(
            status="gray",
            color=color_for("gray"),
            reason="no activity thresholds and too little history to derive them",
            metric_parameter=DISCHARGE_PARAMETER,
            metric_value=discharge.value,
            unit=discharge.unit,
            **base,
        )

    status, reason = classify_value(discharge.value, thresholds)
    percentile = (
        percentile_from_stats(discharge.value, discharge_stats)
        if discharge_stats is not None
        else None
    )
    return SiteCondition(
        status=status,
        color=color_for(status),
        reason=f"{reason} cfs ({thresholds.source.replace('_', ' ')} thresholds)",
        metric_parameter=DISCHARGE_PARAMETER,
        metric_value=discharge.value,
        unit=discharge.unit,
        percentile=percentile,
        thresholds=thresholds,
        **base,
    )


@dataclass(frozen=True, slots=True)
class GageAnchor:
    """A classified gage snapped onto the river network."""

    site: MonitoringSite
    condition: SiteCondition

    @property
    def levelpath_id(self) -> float | None:
        return self.site.levelpath_id

    @property
    def path_length_km(self) -> float | None:
        return self.site.path_length_km


def _drainage_compatible(segment: RiverSegment, site: MonitoringSite) -> bool:
    if segment.drainage_sqkm is None or not site.segment_drainage_sqkm:
        return True
    ratio = segment.drainage_sqkm / site.segment_drainage_sqkm
    return 1 / DRAINAGE_RATIO_LIMIT <= ratio <= DRAINAGE_RATIO_LIMIT


def _mainstem_anchor(
    segment: RiverSegment, anchors: Sequence[GageAnchor], *, max_distance_km: float
) -> tuple[GageAnchor, float] | None:
    if segment.levelpath_id is None or segment.path_length_km is None:
        return None
    best: tuple[GageAnchor, float] | None = None
    for anchor in anchors:
        if anchor.levelpath_id != segment.levelpath_id or anchor.path_length_km is None:
            continue
        if not _drainage_compatible(segment, anchor.site):
            continue
        distance_km = abs(segment.path_length_km - anchor.path_length_km)
        if distance_km <= max_distance_km and (best is None or distance_km < best[1]):
            best = (anchor, distance_km)
    return best


def _proximity_anchor(
    segment: RiverSegment, anchors: Sequence[GageAnchor], *, max_distance_km: float
) -> tuple[GageAnchor, float] | None:
    bbox = bbox_of_multiline(segment.geometry).expanded(max_distance_km * 1000)
    best: tuple[GageAnchor, float] | None = None
    for anchor in anchors:
        site = anchor.site
        if not bbox.contains(site.longitude, site.latitude):
            continue
        distance_km = (
            distance_to_multiline_m(site.longitude, site.latitude, segment.geometry) / 1000.0
        )
        if distance_km <= max_distance_km and (best is None or distance_km < best[1]):
            best = (anchor, distance_km)
    return best


def assign_segment_conditions(
    *,
    huc8: str,
    activity: Activity,
    segments: Sequence[RiverSegment],
    anchors: Sequence[GageAnchor],
    settings: Settings,
    now: datetime,
) -> list[SegmentCondition]:
    """Propagate gage statuses onto flowlines."""
    usable = [anchor for anchor in anchors if anchor.condition.status != "gray"]
    conditions: list[SegmentCondition] = []

    for segment in segments:
        match = _mainstem_anchor(
            segment, usable, max_distance_km=settings.mainstem_assign_distance_km
        )
        assignment = "mainstem"
        if match is None:
            match = _proximity_anchor(
                segment, usable, max_distance_km=settings.proximity_assign_distance_km
            )
            assignment = "proximity"
        if match is None:
            conditions.append(
                SegmentCondition(
                    comid=segment.comid,
                    huc8=huc8,
                    activity=activity,
                    status="gray",
                    color=color_for("gray"),
                    reason="no gage on this mainstem or nearby",
                    computed_at=now,
                )
            )
            continue

        anchor, distance_km = match
        descriptor = (
            f"{anchor.site.name} ({anchor.site.site_number})"
            if assignment == "mainstem"
            else f"{anchor.site.name}, {distance_km:.1f} km away"
        )
        conditions.append(
            SegmentCondition(
                comid=segment.comid,
                huc8=huc8,
                activity=activity,
                status=anchor.condition.status,
                color=anchor.condition.color,
                source_site_id=anchor.site.site_id,
                assignment=assignment,  # type: ignore[arg-type]
                distance_km=round(distance_km, 2),
                reason=f"{anchor.condition.reason} — from {descriptor}",
                computed_at=now,
            )
        )
    return conditions
