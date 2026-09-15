"""Ingest observations for the active gages in a basin.

Per gage this collects four things:

* latest continuous readings (discharge, gage height) — what the map colors by
* a short instantaneous series — the popup trend chart
* daily-values percentiles — the fallback classification when no curated window exists
* discrete channel measurements — fitted into a station velocity rating
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from lib.classify import build_stats
from lib.config import (
    DISCHARGE_PARAMETER,
    GAGE_HEIGHT_PARAMETER,
    BasinConfig,
    Settings,
    get_basin,
    get_settings,
    load_basins,
)
from lib.logs import configure_logging
from lib.models import MonitoringSite, ParameterSeries, Reading, SeriesPoint
from lib.rating import fit_station_rating
from lib.store import ObservationBundle, Store, get_store
from lib.usgs import WaterDataClient

logger = logging.getLogger(__name__)

PARAMETERS = (DISCHARGE_PARAMETER, GAGE_HEIGHT_PARAMETER)


def _as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:  # daily values arrive as plain dates
            parsed = datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_readings(features: Sequence[dict[str, Any]]) -> dict[str, list[Reading]]:
    """Newest reading per (site, parameter) from `latest-continuous` features."""
    newest: dict[tuple[str, str], Reading] = {}
    for feature in features:
        properties = feature.get("properties") or {}
        site_id = properties.get("monitoring_location_id")
        parameter_code = properties.get("parameter_code")
        value = _as_float(properties.get("value"))
        observed_at = _parse_time(properties.get("time"))
        if not site_id or not parameter_code or value is None or observed_at is None:
            continue
        reading = Reading(
            parameter_code=str(parameter_code),
            value=value,
            unit=str(properties.get("unit_of_measure") or ""),
            observed_at=observed_at,
            source="continuous",
            approval_status=properties.get("approval_status"),
            qualifier=properties.get("qualifier"),
        )
        key = (str(site_id), reading.parameter_code)
        current = newest.get(key)
        if current is None or reading.observed_at > current.observed_at:
            newest[key] = reading

    readings: dict[str, list[Reading]] = {}
    for (site_id, _parameter), reading in newest.items():
        readings.setdefault(site_id, []).append(reading)
    for site_readings in readings.values():
        site_readings.sort(key=lambda item: item.parameter_code)
    return readings


def parse_series(
    features: Sequence[dict[str, Any]], *, parameter_code: str
) -> ParameterSeries | None:
    points: list[SeriesPoint] = []
    unit = ""
    for feature in features:
        properties = feature.get("properties") or {}
        value = _as_float(properties.get("value"))
        observed_at = _parse_time(properties.get("time"))
        if value is None or observed_at is None:
            continue
        unit = unit or str(properties.get("unit_of_measure") or "")
        points.append(SeriesPoint(time=observed_at, value=value))
    if not points:
        return None
    points.sort(key=lambda point: point.time)
    return ParameterSeries(parameter_code=parameter_code, unit=unit, points=tuple(points))


def parse_daily_values(features: Sequence[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for feature in features:
        value = _as_float((feature.get("properties") or {}).get("value"))
        if value is not None:
            values.append(value)
    return values


async def _ingest_site(
    site: MonitoringSite,
    *,
    water: WaterDataClient,
    settings: Settings,
    bundle: ObservationBundle,
    now: datetime,
) -> None:
    parameters = sorted(
        {reading.parameter_code for reading in bundle.readings.get(site.site_id, [])}
    )
    series_start = (now - timedelta(hours=settings.series_hours)).isoformat()
    history_start = (now - timedelta(days=settings.history_days)).isoformat()
    end = now.isoformat()

    for parameter_code in parameters:
        features = await water.continuous_series(
            site.site_id, parameter_code=parameter_code, start=series_start, end=end
        )
        series = parse_series(features, parameter_code=parameter_code)
        if series is not None:
            bundle.series.setdefault(site.site_id, []).append(series)

        daily = await water.daily_values(
            site.site_id, parameter_code=parameter_code, start=history_start, end=end
        )
        stats = build_stats(
            parse_daily_values(daily),
            parameter_code=parameter_code,
            window_days=settings.history_days,
        )
        if stats is None:
            # Some gages (small urban creeks especially) publish no approved daily
            # record. Percentiles from raw instantaneous values are autocorrelated and
            # therefore weaker, but they still beat having no thresholds at all.
            history = await water.continuous_series(
                site.site_id,
                parameter_code=parameter_code,
                start=history_start,
                end=end,
                max_points=settings.history_sample_limit,
            )
            history_series = parse_series(history, parameter_code=parameter_code)
            stats = build_stats(
                [point.value for point in history_series.points] if history_series else [],
                parameter_code=parameter_code,
                window_days=settings.history_days,
                source="continuous",
            )
        if stats is not None:
            bundle.stats.setdefault(site.site_id, []).append(stats)

    measurements = await water.channel_measurements(site.site_id)
    rating = fit_station_rating(site.site_id, measurements)
    if rating.measurement_count:
        bundle.ratings[site.site_id] = rating
        if rating.velocity_rating is not None:
            logger.info(
                "%s: velocity rating v=%.4g*Q^%.3g (n=%s, R²=%.2f)",
                site.site_id,
                rating.velocity_rating.k,
                rating.velocity_rating.exponent,
                rating.velocity_rating.count,
                rating.velocity_rating.r_squared,
            )


async def ingest_observations(
    basin: BasinConfig,
    *,
    settings: Settings | None = None,
    store: Store | None = None,
    client: WaterDataClient | None = None,
    now: datetime | None = None,
) -> ObservationBundle:
    settings = settings or get_settings()
    store = store or get_store(settings)
    now = now or datetime.now(UTC)
    sites = store.read_sites(basin.huc8)
    bundle = ObservationBundle(huc8=basin.huc8)
    if not sites:
        logger.warning("%s: no sites stored; run ingest_sites first", basin.huc8)
        return bundle

    owns_client = client is None
    water = client or WaterDataClient(settings=settings)
    try:
        latest = await water.latest_continuous(
            [site.site_id for site in sites], parameter_codes=PARAMETERS
        )
        bundle.readings = parse_readings(latest)
        logger.info(
            "%s: %s gages with fresh readings", basin.huc8, len(bundle.readings)
        )
        await asyncio.gather(
            *(
                _ingest_site(site, water=water, settings=settings, bundle=bundle, now=now)
                for site in sites
                if site.site_id in bundle.readings
            )
        )
    finally:
        if owns_client:
            await water.aclose()

    store.write_observations(bundle)
    return bundle


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--basin", action="append", dest="basins", help="HUC-8 code (repeatable)")
    args = parser.parse_args()
    configure_logging()

    settings = get_settings()
    store = get_store(settings)
    basins = (
        [basin for code in args.basins if (basin := get_basin(code)) is not None]
        if args.basins
        else list(load_basins())
    )
    async with WaterDataClient(settings=settings) as water:
        for basin in basins:
            await ingest_observations(basin, settings=settings, store=store, client=water)


if __name__ == "__main__":
    asyncio.run(main())
