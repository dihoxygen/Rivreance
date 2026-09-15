"""Run the whole Rivreance pipeline: flowlines → sites → observations → conditions.

Typical use::

    # first run (or weekly, to refresh geometry)
    python -m etl.run_pipeline --with-flowlines

    # every 15-30 minutes
    python -m etl.run_pipeline

Every run is written to the `ingestion_runs` audit log, success or failure.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from datetime import UTC, datetime

from etl.compute_conditions import compute_conditions
from etl.ingest_flowlines import ingest_flowlines
from etl.ingest_observations import ingest_observations
from etl.ingest_sites import ingest_sites
from lib.config import ACTIVITIES, Activity, get_basin, get_settings, load_basins
from lib.logs import configure_logging
from lib.models import IngestionRun
from lib.store import Store, get_store
from lib.usgs import FabricClient, WaterDataClient

logger = logging.getLogger(__name__)


async def run_pipeline(
    *,
    basin_codes: list[str] | None = None,
    activities: tuple[Activity, ...] = ACTIVITIES,
    with_flowlines: bool = False,
    store: Store | None = None,
) -> IngestionRun:
    settings = get_settings()
    store = store or get_store(settings)
    basins = (
        [basin for code in basin_codes if (basin := get_basin(code)) is not None]
        if basin_codes
        else list(load_basins())
    )
    if not basins:
        raise SystemExit("no known basins selected; check config/basins.json")

    run = IngestionRun(
        run_id=str(uuid.uuid4()),
        started_at=datetime.now(UTC),
        basins=[basin.huc8 for basin in basins],
    )
    store.write_run(run)
    counts: dict[str, int] = {"segments": 0, "sites": 0, "readings": 0, "conditions": 0}

    try:
        async with WaterDataClient(settings=settings) as water:
            for basin in basins:
                if with_flowlines:
                    async with FabricClient(settings=settings) as fabric:
                        segments = await ingest_flowlines(
                            basin, settings=settings, store=store, client=fabric
                        )
                    counts["segments"] += len(segments)
                else:
                    counts["segments"] += len(store.read_segments(basin.huc8))

                sites = await ingest_sites(
                    basin, settings=settings, store=store, client=water
                )
                counts["sites"] += len(sites)

                observations = await ingest_observations(
                    basin, settings=settings, store=store, client=water
                )
                counts["readings"] += sum(len(items) for items in observations.readings.values())

                for activity in activities:
                    bundle = compute_conditions(
                        basin, activity, settings=settings, store=store
                    )
                    counts["conditions"] += len(bundle.segment_conditions)
    except Exception as error:  # noqa: BLE001 - recorded in the audit log, then re-raised
        run = run.model_copy(
            update={
                "finished_at": datetime.now(UTC),
                "status": "failed",
                "counts": counts,
                "error": f"{type(error).__name__}: {error}",
            }
        )
        store.write_run(run)
        logger.exception("pipeline run %s failed", run.run_id)
        raise

    run = run.model_copy(
        update={"finished_at": datetime.now(UTC), "status": "success", "counts": counts}
    )
    store.write_run(run)
    duration = (run.finished_at - run.started_at).total_seconds()  # type: ignore[operator]
    logger.info("pipeline run %s finished in %.1fs: %s", run.run_id, duration, counts)
    return run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--basin", action="append", dest="basins", help="HUC-8 code (repeatable)")
    parser.add_argument("--activity", action="append", dest="activities", choices=ACTIVITIES)
    parser.add_argument(
        "--with-flowlines",
        action="store_true",
        help="also refresh NHD flowline geometry (slow; needed on the first run)",
    )
    args = parser.parse_args()
    configure_logging()
    asyncio.run(
        run_pipeline(
            basin_codes=args.basins,
            activities=tuple(args.activities) if args.activities else ACTIVITIES,
            with_flowlines=args.with_flowlines,
        )
    )


if __name__ == "__main__":
    main()
