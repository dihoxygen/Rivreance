"""FastAPI service in front of the pipeline output.

Read-only, GeoJSON-first, and cached: the map never talks to USGS directly, so a
crowd of browsers cannot turn into a crowd of USGS requests.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from api.geojson import feature_collection, segment_feature, site_feature
from lib.cache import TtlCache
from lib.config import ACTIVITIES, Activity, Settings, get_basin, get_settings, load_basins
from lib.logs import configure_logging
from lib.store import ConditionBundle, ObservationBundle, Store, get_store

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"

configure_logging()
settings = get_settings()
cache = TtlCache(settings.cache_ttl_seconds)

app = FastAPI(
    title="Rivreance API",
    version="0.1.0",
    description="USGS-derived river conditions for the Black Warrior basins",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_store_dependency() -> Store:
    return get_store(settings)


StoreDep = Annotated[Store, Depends(get_store_dependency)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ActivityQuery = Annotated[Activity, Query(description="Activity profile for thresholds")]


def _cache_headers(response: Response) -> None:
    response.headers["Cache-Control"] = f"public, max-age={settings.cache_ttl_seconds}"


async def _cached(key: str, loader: Any) -> Any:
    return await cache.get_or_set(key, lambda: asyncio.to_thread(loader))


def _require_basin(huc8: str):
    basin = get_basin(huc8)
    if basin is None:
        known = ", ".join(basin.huc8 for basin in load_basins())
        raise HTTPException(status_code=404, detail=f"unknown basin {huc8}; known basins: {known}")
    return basin


def _validate_activity(activity: str) -> Activity:
    if activity not in ACTIVITIES:
        raise HTTPException(
            status_code=422, detail=f"activity must be one of {', '.join(ACTIVITIES)}"
        )
    return activity  # type: ignore[return-value]


@app.get(f"{API_PREFIX}/health")
async def health(store: StoreDep, config: SettingsDep) -> dict[str, Any]:
    """Pipeline freshness — what a monitor (or the map's warning banner) should poll.

    Deliberately uncached: a cached answer would report its own age as the data's age,
    which is the one thing this endpoint exists to get right.
    """
    run = await asyncio.to_thread(store.read_latest_run)
    now = datetime.now(UTC)
    age_minutes = None
    if run is not None and run.finished_at is not None:
        age_minutes = round((now - run.finished_at).total_seconds() / 60.0, 1)
    return {
        "status": "ok" if run is not None and run.status == "success" else "degraded",
        "store_backend": config.store_backend,
        "checked_at": now.isoformat(),
        "last_run": run.model_dump(mode="json") if run else None,
        "last_run_age_minutes": age_minutes,
        "stale": age_minutes is None or age_minutes > config.stale_after_minutes,
        "activities": list(ACTIVITIES),
    }


@app.get(f"{API_PREFIX}/basins")
async def list_basins(response: Response) -> dict[str, Any]:
    _cache_headers(response)
    return {
        "basins": [
            {
                "huc8": basin.huc8,
                "name": basin.name,
                "bbox": list(basin.bbox),
                "center": list(basin.center),
                "default_zoom": basin.default_zoom,
            }
            for basin in load_basins()
        ]
    }


@app.get(f"{API_PREFIX}/basins/{{huc8}}/segments")
async def basin_segments(
    huc8: str,
    response: Response,
    store: StoreDep,
    activity: ActivityQuery = "kayaking",
    min_order: Annotated[int, Query(ge=1, le=10)] = 1,
) -> dict[str, Any]:
    """River segments as GeoJSON, colored for the requested activity."""
    basin = _require_basin(huc8)
    activity = _validate_activity(activity)
    _cache_headers(response)

    segments = await _cached(f"segments:{huc8}", lambda: store.read_segments(huc8))
    bundle: ConditionBundle = await _cached(
        f"conditions:{huc8}:{activity}", lambda: store.read_conditions(huc8, activity)
    )
    conditions = {condition.comid: condition for condition in bundle.segment_conditions}

    features = [
        segment_feature(segment, conditions.get(segment.comid))
        for segment in segments
        if (segment.stream_order or 0) >= min_order
    ]
    tally = Counter(feature["properties"]["status"] for feature in features)
    computed_at = max(
        (condition.computed_at for condition in bundle.segment_conditions), default=None
    )
    return feature_collection(
        features,
        basin={"huc8": basin.huc8, "name": basin.name},
        activity=activity,
        status_counts=dict(tally),
        computed_at=computed_at.isoformat() if computed_at else None,
    )


@app.get(f"{API_PREFIX}/basins/{{huc8}}/sites")
async def basin_sites(
    huc8: str,
    response: Response,
    store: StoreDep,
    activity: ActivityQuery = "kayaking",
) -> dict[str, Any]:
    """Gage points with their latest readings, condition, and velocity estimate."""
    basin = _require_basin(huc8)
    activity = _validate_activity(activity)
    _cache_headers(response)

    sites = await _cached(f"sites:{huc8}", lambda: store.read_sites(huc8))
    observations: ObservationBundle = await _cached(
        f"observations:{huc8}", lambda: store.read_observations(huc8)
    )
    bundle: ConditionBundle = await _cached(
        f"conditions:{huc8}:{activity}", lambda: store.read_conditions(huc8, activity)
    )
    conditions = {condition.site_id: condition for condition in bundle.site_conditions}

    features = [
        site_feature(
            site,
            conditions.get(site.site_id),
            rating=observations.ratings.get(site.site_id),
            series=observations.series.get(site.site_id, []),
        )
        for site in sites
    ]
    return feature_collection(
        features,
        basin={"huc8": basin.huc8, "name": basin.name},
        activity=activity,
        status_counts=dict(Counter(feature["properties"]["status"] for feature in features)),
    )


@app.get(f"{API_PREFIX}/sites/{{site_id}}/series")
async def site_series(
    site_id: str,
    response: Response,
    store: StoreDep,
    parameter: Annotated[str, Query(pattern=r"^\d{5}$")] = "00060",
) -> dict[str, Any]:
    """Recent instantaneous values for one gage — the popup trend chart."""
    _cache_headers(response)
    for basin in load_basins():
        observations: ObservationBundle = await _cached(
            f"observations:{basin.huc8}", lambda basin=basin: store.read_observations(basin.huc8)
        )
        for series in observations.series.get(site_id, []):
            if series.parameter_code == parameter:
                return {
                    "site_id": site_id,
                    "parameter_code": series.parameter_code,
                    "unit": series.unit,
                    "points": [point.model_dump(mode="json") for point in series.points],
                }
    raise HTTPException(
        status_code=404, detail=f"no cached series for {site_id} parameter {parameter}"
    )
