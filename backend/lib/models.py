"""Pydantic models shared by the ETL, the store, and the API.

These are the wire format for the JSON snapshot store and map 1:1 onto the
Supabase tables in `supabase/migrations/0001_init_rivreance.sql`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from lib.config import Activity

Status = Literal["green", "yellow", "red", "gray"]
ObservationSource = Literal["continuous", "field"]
Assignment = Literal["mainstem", "proximity", "unassigned"]
VelocityMethod = Literal[
    "field_rating",
    "field_area_rating",
    "cross_section",
    "manning",
    "nhdplus_erom",
]
Confidence = Literal["high", "medium", "low"]

STATUS_COLORS: dict[Status, str] = {
    "green": "#1a9850",
    "yellow": "#f6c344",
    "red": "#d73027",
    "gray": "#9aa0a6",
}


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Reading(Frozen):
    """One observed value for a parameter at a gage."""

    parameter_code: str
    value: float
    unit: str
    observed_at: datetime
    source: ObservationSource = "continuous"
    approval_status: str | None = None
    qualifier: str | None = None


class SeriesPoint(Frozen):
    time: datetime
    value: float


class ParameterSeries(Frozen):
    """Recent instantaneous history for one parameter, used by popup charts."""

    parameter_code: str
    unit: str
    points: tuple[SeriesPoint, ...] = ()


class ParameterStats(Frozen):
    """Percentiles from the daily-values record, used when no curated threshold exists."""

    parameter_code: str
    window_days: int
    count: int
    #: Which collection the record came from: approved daily means, or, for stations
    #: that publish no daily record, raw instantaneous values.
    source: Literal["daily", "continuous"] = "daily"
    p05: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    p95: float


class PowerLawRating(Frozen):
    r"""Empirical fit of the form ``y = k * Q^exponent`` (log-log least squares)."""

    k: float
    exponent: float
    count: int
    r_squared: float
    q_min: float
    q_max: float


class CrossSection(Frozen):
    """Trapezoidal channel approximation used for the Q/A velocity estimate."""

    bottom_width_ft: float
    side_slope: float = 2.0
    #: Gage height at which flow depth is zero (stage of zero flow).
    zero_flow_stage_ft: float = 0.0
    manning_n: float = 0.035
    channel_slope: float | None = None
    source: str = "configured"


class StationRating(Frozen):
    """Velocity/area ratings fitted from USGS discrete channel measurements."""

    site_id: str
    velocity_rating: PowerLawRating | None = None
    area_rating: PowerLawRating | None = None
    median_width_ft: float | None = None
    measurement_count: int = 0
    fitted_at: datetime | None = None


class VelocityEstimate(Frozen):
    """Estimated mean channel velocity with provenance."""

    velocity_fps: float
    velocity_mph: float
    method: VelocityMethod
    confidence: Confidence
    area_sqft: float | None = None
    hydraulic_radius_ft: float | None = None
    note: str | None = None


class ActivityThresholds(Frozen):
    """Flow window that defines unsafe / cautionary / optimal conditions."""

    activity: Activity
    parameter_code: str = "00060"
    min_cfs: float
    opt_min_cfs: float
    opt_max_cfs: float
    max_cfs: float
    source: str = "curated"
    note: str | None = None


class MonitoringSite(BaseModel):
    """A USGS gage in one of the MVP basins."""

    site_id: str
    site_number: str
    name: str
    latitude: float
    longitude: float
    huc8: str
    huc12: str | None = None
    site_type: str | None = None
    drainage_area_sqmi: float | None = None
    flood_stage_ft: float | None = None
    # Populated by the flowline snap step.
    comid: int | None = None
    levelpath_id: float | None = None
    path_length_km: float | None = None
    segment_drainage_sqkm: float | None = None
    snap_distance_m: float | None = None


class RiverSegment(BaseModel):
    """An NHDPlus v2 flowline in the basin (the line we color)."""

    comid: int
    huc8: str
    name: str | None = None
    reach_code: str | None = None
    stream_order: int | None = None
    length_km: float | None = None
    slope: float | None = None
    levelpath_id: float | None = None
    path_length_km: float | None = None
    drainage_sqkm: float | None = None
    #: NHDPlus EROM mean-annual discharge (cfs) and velocity (fps) for the reach.
    erom_flow_cfs: float | None = None
    erom_velocity_fps: float | None = None
    #: GeoJSON MultiLineString coordinates.
    geometry: list[list[list[float]]]


class SiteCondition(BaseModel):
    """Classified condition for one gage and one activity."""

    site_id: str
    activity: Activity
    status: Status
    color: str
    reason: str
    metric_parameter: str | None = None
    metric_value: float | None = None
    unit: str | None = None
    observed_at: datetime | None = None
    age_minutes: float | None = None
    discharge_cfs: float | None = None
    gage_height_ft: float | None = None
    percentile: float | None = None
    thresholds: ActivityThresholds | None = None
    velocity: VelocityEstimate | None = None
    trend: Literal["rising", "falling", "steady", "unknown"] = "unknown"


class SegmentCondition(BaseModel):
    """Condition propagated from a gage onto a river segment."""

    comid: int
    huc8: str
    activity: Activity
    status: Status
    color: str
    source_site_id: str | None = None
    assignment: Assignment = "unassigned"
    distance_km: float | None = None
    reason: str = "no nearby gage"
    computed_at: datetime


class IngestionRun(BaseModel):
    """Audit record for one pipeline execution."""

    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    status: Literal["running", "success", "failed"] = "running"
    basins: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    error: str | None = None
