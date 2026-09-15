r"""Fit per-station power-law ratings from USGS discrete channel measurements.

The `channel-measurements` collection publishes paired discharge, area, width, and
velocity from field visits. Fitting :math:`\log y = \log k + m \log Q` by ordinary
least squares turns those visits into a station-specific rating, which is far more
trustworthy than a guessed channel geometry.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from lib.models import PowerLawRating, StationRating

MIN_FIT_POINTS = 4


def fit_power_law(pairs: Sequence[tuple[float, float]]) -> PowerLawRating | None:
    """Least-squares fit of ``y = k * x^m`` in log space.

    Returns `None` when there are too few usable points or the discharges do not
    span a range (a single discharge cannot constrain an exponent).
    """
    samples = [(x, y) for x, y in pairs if x > 0 and y > 0]
    if len(samples) < MIN_FIT_POINTS:
        return None

    log_x = [math.log(x) for x, _ in samples]
    log_y = [math.log(y) for _, y in samples]
    mean_x = statistics.fmean(log_x)
    mean_y = statistics.fmean(log_y)
    variance_x = sum((value - mean_x) ** 2 for value in log_x)
    if variance_x <= 1e-9:
        return None

    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(log_x, log_y, strict=True))
    exponent = covariance / variance_x
    intercept = mean_y - exponent * mean_x

    residual_ss = sum(
        (y - (intercept + exponent * x)) ** 2 for x, y in zip(log_x, log_y, strict=True)
    )
    total_ss = sum((y - mean_y) ** 2 for y in log_y)
    r_squared = 1.0 - residual_ss / total_ss if total_ss > 1e-12 else 0.0

    discharges = [x for x, _ in samples]
    return PowerLawRating(
        k=math.exp(intercept),
        exponent=exponent,
        count=len(samples),
        r_squared=max(0.0, min(1.0, r_squared)),
        q_min=min(discharges),
        q_max=max(discharges),
    )


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _to_fps(value: float, unit: str | None) -> float | None:
    """Normalize a velocity to feet per second."""
    match (unit or "ft/s").strip().lower():
        case "ft/s" | "ft/sec" | "fps" | "feet per second":
            return value
        case "m/s" | "m/sec" | "meters per second":
            return value * 3.28084
        case "mph" | "mi/h":
            return value * 5280.0 / 3600.0
        case _:
            return None


def _to_sqft(value: float, unit: str | None) -> float | None:
    match (unit or "ft^2").strip().lower():
        case "ft^2" | "ft2" | "sq ft" | "square feet":
            return value
        case "m^2" | "m2" | "square meters":
            return value * 10.7639
        case _:
            return None


def _to_ft(value: float, unit: str | None) -> float | None:
    match (unit or "ft").strip().lower():
        case "ft" | "feet":
            return value
        case "m" | "meters":
            return value * 3.28084
        case _:
            return None


def fit_station_rating(
    site_id: str, measurements: Iterable[dict[str, Any]], *, max_age_years: float = 15.0
) -> StationRating:
    """Build velocity and area ratings from `channel-measurements` GeoJSON features."""
    now = datetime.now(UTC)
    velocity_pairs: list[tuple[float, float]] = []
    area_pairs: list[tuple[float, float]] = []
    widths: list[float] = []
    used = 0

    for feature in measurements:
        properties = feature.get("properties", feature)
        discharge = _as_float(properties.get("channel_flow"))
        if discharge is None or discharge <= 0:
            continue

        observed_at = properties.get("time")
        if isinstance(observed_at, str):
            try:
                measured = datetime.fromisoformat(observed_at)
            except ValueError:
                measured = None
            if measured is not None:
                if measured.tzinfo is None:
                    measured = measured.replace(tzinfo=UTC)
                if (now - measured).days > max_age_years * 365.25:
                    continue

        used += 1
        raw_velocity = _as_float(properties.get("channel_velocity"))
        if raw_velocity is not None and raw_velocity > 0:
            velocity_fps = _to_fps(raw_velocity, properties.get("channel_velocity_unit"))
            if velocity_fps is not None:
                velocity_pairs.append((discharge, velocity_fps))

        raw_area = _as_float(properties.get("channel_area"))
        if raw_area is not None and raw_area > 0:
            area_sqft = _to_sqft(raw_area, properties.get("channel_area_unit"))
            if area_sqft is not None:
                area_pairs.append((discharge, area_sqft))

        raw_width = _as_float(properties.get("channel_width"))
        if raw_width is not None and raw_width > 0:
            width_ft = _to_ft(raw_width, properties.get("channel_width_unit"))
            if width_ft is not None:
                widths.append(width_ft)

    return StationRating(
        site_id=site_id,
        velocity_rating=fit_power_law(velocity_pairs),
        area_rating=fit_power_law(area_pairs),
        median_width_ft=statistics.median(widths) if widths else None,
        measurement_count=used,
        fitted_at=now,
    )
