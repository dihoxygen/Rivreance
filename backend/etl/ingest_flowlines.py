"""Ingest NHDPlus v2 flowlines for a basin from the USGS geospatial Fabric.

Flowline geometry changes on the order of years, so this step is separate from the
15-minute observation refresh: run it once per basin, then weekly at most.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from lib.config import BasinConfig, Settings, get_basin, get_settings, load_basins
from lib.geo import Bbox
from lib.logs import configure_logging
from lib.models import RiverSegment
from lib.store import Store, get_store
from lib.usgs import FabricClient

logger = logging.getLogger(__name__)


def _as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _clean_name(value: Any) -> str | None:
    name = str(value or "").strip()
    return name or None


def flowline_to_segment(feature: dict[str, Any], huc8: str) -> RiverSegment | None:
    """Convert a Fabric flowline feature into a `RiverSegment`.

    Returns `None` for features without usable geometry or a comid.
    """
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    comid = properties.get("comid")
    if comid is None:
        return None

    coordinates = geometry.get("coordinates") or []
    if geometry.get("type") == "LineString":
        coordinates = [coordinates]
    lines = [
        [[float(point[0]), float(point[1])] for point in line]
        for line in coordinates
        if len(line) > 1
    ]
    if not lines:
        return None

    stream_order = _as_float(properties.get("streamorde"))
    return RiverSegment(
        comid=int(comid),
        huc8=huc8,
        name=_clean_name(properties.get("gnis_name")),
        reach_code=_clean_name(properties.get("reachcode")),
        stream_order=int(stream_order) if stream_order is not None else None,
        length_km=_as_float(properties.get("lengthkm")),
        slope=_as_float(properties.get("slope")),
        levelpath_id=_as_float(properties.get("levelpathi")),
        path_length_km=_as_float(properties.get("pathlength")),
        drainage_sqkm=_as_float(properties.get("totdasqkm")),
        erom_flow_cfs=_as_float(properties.get("qe_ma")),
        erom_velocity_fps=_as_float(properties.get("ve_ma")),
        geometry=lines,
    )


def in_basin(segment: RiverSegment, huc8: str) -> bool:
    """NHD reach codes start with the HUC-8, which trims bbox overspill precisely."""
    return bool(segment.reach_code and segment.reach_code.startswith(huc8))


async def ingest_flowlines(
    basin: BasinConfig,
    *,
    settings: Settings | None = None,
    store: Store | None = None,
    client: FabricClient | None = None,
) -> list[RiverSegment]:
    settings = settings or get_settings()
    store = store or get_store(settings)
    owns_client = client is None
    fabric = client or FabricClient(settings=settings)

    try:
        bbox = Bbox(*basin.bbox)
        logger.info(
            "fetching flowlines for %s (%s) bbox=%s", basin.huc8, basin.name, bbox.as_param()
        )
        features = await fabric.flowlines(bbox)
    finally:
        if owns_client:
            await fabric.aclose()

    segments: list[RiverSegment] = []
    for feature in features:
        segment = flowline_to_segment(feature, basin.huc8)
        if segment is None or not in_basin(segment, basin.huc8):
            continue
        if segment.stream_order is not None and segment.stream_order < settings.min_stream_order:
            continue
        segments.append(segment)

    segments.sort(key=lambda segment: segment.comid)
    logger.info(
        "%s: kept %s of %s flowlines (order >= %s, reach code in basin)",
        basin.huc8,
        len(segments),
        len(features),
        settings.min_stream_order,
    )
    store.write_segments(basin.huc8, segments)
    return segments


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
    async with FabricClient(settings=settings) as fabric:
        for basin in basins:
            await ingest_flowlines(basin, settings=settings, store=store, client=fabric)


if __name__ == "__main__":
    asyncio.run(main())
