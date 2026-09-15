"""Classify stored observations and propagate the result onto river segments.

Runs entirely on stored data, so it is cheap to re-run after tuning thresholds.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime

from lib.conditions import GageAnchor, assign_segment_conditions, build_site_condition
from lib.config import (
    ACTIVITIES,
    Activity,
    BasinConfig,
    Settings,
    get_basin,
    get_settings,
    load_basins,
)
from lib.logs import configure_logging
from lib.store import ConditionBundle, Store, get_store

logger = logging.getLogger(__name__)


def compute_conditions(
    basin: BasinConfig,
    activity: Activity,
    *,
    settings: Settings | None = None,
    store: Store | None = None,
    now: datetime | None = None,
) -> ConditionBundle:
    settings = settings or get_settings()
    store = store or get_store(settings)
    now = now or datetime.now(UTC)

    sites = store.read_sites(basin.huc8)
    segments = store.read_segments(basin.huc8)
    observations = store.read_observations(basin.huc8)
    segments_by_comid = {segment.comid: segment for segment in segments}

    anchors: list[GageAnchor] = []
    for site in sites:
        condition = build_site_condition(
            site=site,
            activity=activity,
            readings=observations.readings.get(site.site_id, []),
            series=observations.series.get(site.site_id, []),
            stats=observations.stats.get(site.site_id, []),
            rating=observations.ratings.get(site.site_id),
            segment=segments_by_comid.get(site.comid) if site.comid else None,
            settings=settings,
            now=now,
        )
        anchors.append(GageAnchor(site=site, condition=condition))

    segment_conditions = assign_segment_conditions(
        huc8=basin.huc8,
        activity=activity,
        segments=segments,
        anchors=anchors,
        settings=settings,
        now=now,
    )

    tally: dict[str, int] = {}
    for condition in segment_conditions:
        tally[condition.status] = tally.get(condition.status, 0) + 1
    logger.info(
        "%s/%s: %s gages classified, %s segments colored %s",
        basin.huc8,
        activity,
        len(anchors),
        len(segment_conditions),
        tally,
    )

    bundle = ConditionBundle(
        huc8=basin.huc8,
        activity=activity,
        site_conditions=[anchor.condition for anchor in anchors],
        segment_conditions=segment_conditions,
    )
    store.write_conditions(bundle)
    return bundle


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--basin", action="append", dest="basins", help="HUC-8 code (repeatable)")
    parser.add_argument("--activity", action="append", dest="activities", choices=ACTIVITIES)
    args = parser.parse_args()
    configure_logging()

    settings = get_settings()
    store = get_store(settings)
    basins = (
        [basin for code in args.basins if (basin := get_basin(code)) is not None]
        if args.basins
        else list(load_basins())
    )
    for basin in basins:
        for activity in args.activities or ACTIVITIES:
            compute_conditions(basin, activity, settings=settings, store=store)


if __name__ == "__main__":
    asyncio.run(main())
