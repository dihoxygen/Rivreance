"""Ingest USGS gages for a basin and snap each one to its NHD flowline.

Only stream gages that have reported discharge or gage height recently are kept —
the basin also holds hundreds of retired or non-stream sites that would otherwise
clutter the map.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from lib.config import (
    DISCHARGE_PARAMETER,
    GAGE_HEIGHT_PARAMETER,
    BasinConfig,
    Settings,
    get_basin,
    get_settings,
    load_basins,
)
from lib.geo import bbox_of_multiline, distance_to_multiline_m
from lib.logs import configure_logging
from lib.models import MonitoringSite, RiverSegment
from lib.store import Store, get_store
from lib.usgs import WaterDataClient

logger = logging.getLogger(__name__)


def parse_site(feature: dict[str, Any], huc8: str) -> MonitoringSite | None:
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    site_id = properties.get("id")
    if not site_id or len(coordinates) < 2:
        return None

    drainage_area = properties.get("drainage_area")
    return MonitoringSite(
        site_id=str(site_id),
        site_number=str(properties.get("monitoring_location_number") or site_id).strip(),
        name=str(properties.get("monitoring_location_name") or site_id).strip().title(),
        longitude=float(coordinates[0]),
        latitude=float(coordinates[1]),
        huc8=huc8,
        huc12=properties.get("hydrologic_unit_code"),
        site_type=properties.get("site_type"),
        drainage_area_sqmi=float(drainage_area) if drainage_area is not None else None,
    )


def parse_reading_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def active_site_ids(
    latest_features: Sequence[dict[str, Any]], *, now: datetime, inactive_after_days: int
) -> set[str]:
    """Site ids with at least one reading inside the activity window.

    `latest-continuous` also returns the final reading of long-retired time series,
    so the age filter is what separates live gages from historical ones.
    """
    cutoff = now - timedelta(days=inactive_after_days)
    active: set[str] = set()
    for feature in latest_features:
        properties = feature.get("properties") or {}
        observed_at = parse_reading_time(properties.get("time"))
        if observed_at is not None and observed_at >= cutoff:
            active.add(str(properties.get("monitoring_location_id")))
    return active


def snap_sites_to_segments(
    sites: Sequence[MonitoringSite], segments: Sequence[RiverSegment], *, max_distance_m: float
) -> None:
    """Attach the nearest flowline (and its mainstem attributes) to each site, in place."""
    if not segments:
        logger.warning("no flowlines available; sites will not be snapped")
        return

    boxes = [(segment, bbox_of_multiline(segment.geometry)) for segment in segments]
    for site in sites:
        best: tuple[float, RiverSegment] | None = None
        for segment, bbox in boxes:
            if not bbox.expanded(max_distance_m).contains(site.longitude, site.latitude):
                continue
            distance = distance_to_multiline_m(site.longitude, site.latitude, segment.geometry)
            if distance <= max_distance_m and (best is None or distance < best[0]):
                best = (distance, segment)
        if best is None:
            logger.info("site %s has no flowline within %.0f m", site.site_id, max_distance_m)
            continue
        distance, segment = best
        site.comid = segment.comid
        site.levelpath_id = segment.levelpath_id
        site.path_length_km = segment.path_length_km
        site.segment_drainage_sqkm = segment.drainage_sqkm
        site.snap_distance_m = round(distance, 1)


async def ingest_sites(
    basin: BasinConfig,
    *,
    settings: Settings | None = None,
    store: Store | None = None,
    client: WaterDataClient | None = None,
    now: datetime | None = None,
) -> list[MonitoringSite]:
    settings = settings or get_settings()
    store = store or get_store(settings)
    now = now or datetime.now(UTC)
    owns_client = client is None
    water = client or WaterDataClient(settings=settings)

    try:
        features = await water.monitoring_locations(huc=basin.huc8)
        candidates = [
            site for feature in features if (site := parse_site(feature, basin.huc8)) is not None
        ]
        logger.info("%s: %s stream sites in the hydrologic unit", basin.huc8, len(candidates))
        if not candidates:
            store.write_sites(basin.huc8, [])
            return []

        latest = await water.latest_continuous(
            [site.site_id for site in candidates],
            parameter_codes=(DISCHARGE_PARAMETER, GAGE_HEIGHT_PARAMETER),
        )
    finally:
        if owns_client:
            await water.aclose()

    active = active_site_ids(latest, now=now, inactive_after_days=settings.inactive_after_days)
    sites = [site for site in candidates if site.site_id in active]
    logger.info(
        "%s: %s gages reporting within %s days",
        basin.huc8,
        len(sites),
        settings.inactive_after_days,
    )

    snap_sites_to_segments(
        sites, store.read_segments(basin.huc8), max_distance_m=settings.gage_snap_distance_m
    )
    sites.sort(key=lambda site: site.site_number)
    store.write_sites(basin.huc8, sites)
    return sites


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
            await ingest_sites(basin, settings=settings, store=store, client=water)


if __name__ == "__main__":
    asyncio.run(main())
