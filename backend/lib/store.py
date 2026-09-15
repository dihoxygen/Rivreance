"""Persistence for pipeline output.

Two interchangeable backends implement the same `Store` protocol:

* `FileStore` — JSON snapshots under `backend/.data`. The default, so the prototype
  runs with no cloud credentials.
* `SupabaseStore` — PostgREST calls against the Supabase schema in
  `supabase/migrations`. Uses the service-role key, so it is backend-only.

Pick one with `RIVREANCE_STORE_BACKEND=file|supabase`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

from lib.config import Activity, Settings, get_settings
from lib.models import (
    IngestionRun,
    MonitoringSite,
    ParameterSeries,
    ParameterStats,
    Reading,
    RiverSegment,
    SegmentCondition,
    SiteCondition,
    StationRating,
)

logger = logging.getLogger(__name__)


class ObservationBundle(BaseModel):
    """Everything observed for a basin in one ETL pass."""

    huc8: str
    readings: dict[str, list[Reading]] = Field(default_factory=dict)
    series: dict[str, list[ParameterSeries]] = Field(default_factory=dict)
    stats: dict[str, list[ParameterStats]] = Field(default_factory=dict)
    ratings: dict[str, StationRating] = Field(default_factory=dict)


class ConditionBundle(BaseModel):
    """Classified output for one basin and activity."""

    huc8: str
    activity: Activity
    site_conditions: list[SiteCondition] = Field(default_factory=list)
    segment_conditions: list[SegmentCondition] = Field(default_factory=list)


class Store(Protocol):
    def write_sites(self, huc8: str, sites: list[MonitoringSite]) -> None: ...
    def read_sites(self, huc8: str) -> list[MonitoringSite]: ...
    def write_segments(self, huc8: str, segments: list[RiverSegment]) -> None: ...
    def read_segments(self, huc8: str) -> list[RiverSegment]: ...
    def write_observations(self, bundle: ObservationBundle) -> None: ...
    def read_observations(self, huc8: str) -> ObservationBundle: ...
    def write_conditions(self, bundle: ConditionBundle) -> None: ...
    def read_conditions(self, huc8: str, activity: Activity) -> ConditionBundle: ...
    def write_run(self, run: IngestionRun) -> None: ...
    def read_latest_run(self) -> IngestionRun | None: ...


class FileStore:
    """JSON snapshot store; one directory per basin."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)

    def _basin_dir(self, huc8: str) -> Path:
        path = self.data_dir / huc8
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)

    def _read_json(self, path: Path) -> Any | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write_sites(self, huc8: str, sites: list[MonitoringSite]) -> None:
        self._write_json(
            self._basin_dir(huc8) / "sites.json", [site.model_dump(mode="json") for site in sites]
        )

    def read_sites(self, huc8: str) -> list[MonitoringSite]:
        payload = self._read_json(self.data_dir / huc8 / "sites.json") or []
        return [MonitoringSite.model_validate(item) for item in payload]

    def write_segments(self, huc8: str, segments: list[RiverSegment]) -> None:
        self._write_json(
            self._basin_dir(huc8) / "segments.json",
            [segment.model_dump(mode="json") for segment in segments],
        )

    def read_segments(self, huc8: str) -> list[RiverSegment]:
        payload = self._read_json(self.data_dir / huc8 / "segments.json") or []
        return [RiverSegment.model_validate(item) for item in payload]

    def write_observations(self, bundle: ObservationBundle) -> None:
        self._write_json(
            self._basin_dir(bundle.huc8) / "observations.json", bundle.model_dump(mode="json")
        )

    def read_observations(self, huc8: str) -> ObservationBundle:
        payload = self._read_json(self.data_dir / huc8 / "observations.json")
        if payload is None:
            return ObservationBundle(huc8=huc8)
        return ObservationBundle.model_validate(payload)

    def write_conditions(self, bundle: ConditionBundle) -> None:
        self._write_json(
            self._basin_dir(bundle.huc8) / f"conditions-{bundle.activity}.json",
            bundle.model_dump(mode="json"),
        )

    def read_conditions(self, huc8: str, activity: Activity) -> ConditionBundle:
        payload = self._read_json(self.data_dir / huc8 / f"conditions-{activity}.json")
        if payload is None:
            return ConditionBundle(huc8=huc8, activity=activity)
        return ConditionBundle.model_validate(payload)

    def write_run(self, run: IngestionRun) -> None:
        path = self.data_dir / "runs.json"
        history = self._read_json(path) or []
        history = [item for item in history if item.get("run_id") != run.run_id]
        history.append(run.model_dump(mode="json"))
        self._write_json(path, history[-50:])

    def read_latest_run(self) -> IngestionRun | None:
        history = self._read_json(self.data_dir / "runs.json") or []
        completed = [IngestionRun.model_validate(item) for item in history]
        if not completed:
            return None
        return max(completed, key=lambda run: run.started_at)


def _multiline_to_ewkt(coordinates: list[list[list[float]]]) -> str:
    parts = [
        "(" + ",".join(f"{point[0]} {point[1]}" for point in line) + ")"
        for line in coordinates
        if line
    ]
    return f"SRID=4326;MULTILINESTRING({','.join(parts)})"


class SupabaseStore:
    """PostgREST-backed store. Requires `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError(
                "store_backend='supabase' needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"
            )
        self._settings = settings
        key = settings.supabase_service_role_key
        self._client = client or httpx.Client(
            base_url=settings.supabase_url.rstrip("/") + "/rest/v1",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(settings.request_timeout_seconds),
        )

    def _upsert(self, table: str, rows: list[dict[str, Any]], *, on_conflict: str) -> None:
        if not rows:
            return
        for start in range(0, len(rows), 500):
            response = self._client.post(
                f"/{table}",
                params={"on_conflict": on_conflict},
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
                json=rows[start : start + 500],
            )
            response.raise_for_status()

    def _select(self, table: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        response = self._client.get(f"/{table}", params=params)
        response.raise_for_status()
        return response.json()

    def write_sites(self, huc8: str, sites: list[MonitoringSite]) -> None:
        self._upsert(
            "monitoring_sites",
            [site.model_dump(mode="json") for site in sites],
            on_conflict="site_id",
        )

    def read_sites(self, huc8: str) -> list[MonitoringSite]:
        rows = self._select("monitoring_sites", {"huc8": f"eq.{huc8}", "select": "*"})
        return [MonitoringSite.model_validate(row) for row in rows]

    def write_segments(self, huc8: str, segments: list[RiverSegment]) -> None:
        rows = []
        for segment in segments:
            row = segment.model_dump(mode="json")
            row["geom"] = _multiline_to_ewkt(row.pop("geometry"))
            rows.append(row)
        self._upsert("river_segments", rows, on_conflict="comid")

    def read_segments(self, huc8: str) -> list[RiverSegment]:
        rows = self._select("v_river_segments", {"huc8": f"eq.{huc8}", "select": "*"})
        return [RiverSegment.model_validate(row) for row in rows]

    def write_observations(self, bundle: ObservationBundle) -> None:
        readings = [
            {"site_id": site_id, **reading.model_dump(mode="json")}
            for site_id, site_readings in bundle.readings.items()
            for reading in site_readings
        ]
        self._upsert(
            "observations", readings, on_conflict="site_id,parameter_code,observed_at,source"
        )

        series_rows = [
            {
                "site_id": site_id,
                "parameter_code": series.parameter_code,
                "unit": series.unit,
                "points": [point.model_dump(mode="json") for point in series.points],
            }
            for site_id, site_series in bundle.series.items()
            for series in site_series
        ]
        self._upsert("site_series", series_rows, on_conflict="site_id,parameter_code")

        stats_rows = [
            {"site_id": site_id, **stats.model_dump(mode="json")}
            for site_id, site_stats in bundle.stats.items()
            for stats in site_stats
        ]
        self._upsert("parameter_stats", stats_rows, on_conflict="site_id,parameter_code")

        rating_rows = [rating.model_dump(mode="json") for rating in bundle.ratings.values()]
        self._upsert("station_ratings", rating_rows, on_conflict="site_id")

    def read_observations(self, huc8: str) -> ObservationBundle:
        bundle = ObservationBundle(huc8=huc8)
        site_ids = [site.site_id for site in self.read_sites(huc8)]
        if not site_ids:
            return bundle
        site_filter = f"in.({','.join(site_ids)})"

        for row in self._select(
            "observations", {"site_id": site_filter, "select": "*", "order": "observed_at.desc"}
        ):
            site_id = row.pop("site_id")
            bundle.readings.setdefault(site_id, []).append(Reading.model_validate(row))
        for row in self._select("site_series", {"site_id": site_filter, "select": "*"}):
            site_id = row.pop("site_id")
            bundle.series.setdefault(site_id, []).append(ParameterSeries.model_validate(row))
        for row in self._select("parameter_stats", {"site_id": site_filter, "select": "*"}):
            site_id = row.pop("site_id")
            bundle.stats.setdefault(site_id, []).append(ParameterStats.model_validate(row))
        for row in self._select("station_ratings", {"site_id": site_filter, "select": "*"}):
            bundle.ratings[row["site_id"]] = StationRating.model_validate(row)
        return bundle

    def write_conditions(self, bundle: ConditionBundle) -> None:
        self._upsert(
            "site_conditions",
            [condition.model_dump(mode="json") for condition in bundle.site_conditions],
            on_conflict="site_id,activity",
        )
        self._upsert(
            "segment_conditions",
            [condition.model_dump(mode="json") for condition in bundle.segment_conditions],
            on_conflict="comid,activity",
        )

    def read_conditions(self, huc8: str, activity: Activity) -> ConditionBundle:
        site_ids = [site.site_id for site in self.read_sites(huc8)]
        site_conditions: list[SiteCondition] = []
        if site_ids:
            site_conditions = [
                SiteCondition.model_validate(row)
                for row in self._select(
                    "site_conditions",
                    {
                        "site_id": f"in.({','.join(site_ids)})",
                        "activity": f"eq.{activity}",
                        "select": "*",
                    },
                )
            ]
        segment_conditions = [
            SegmentCondition.model_validate(row)
            for row in self._select(
                "segment_conditions",
                {"huc8": f"eq.{huc8}", "activity": f"eq.{activity}", "select": "*"},
            )
        ]
        return ConditionBundle(
            huc8=huc8,
            activity=activity,
            site_conditions=site_conditions,
            segment_conditions=segment_conditions,
        )

    def write_run(self, run: IngestionRun) -> None:
        self._upsert("ingestion_runs", [run.model_dump(mode="json")], on_conflict="run_id")

    def read_latest_run(self) -> IngestionRun | None:
        rows = self._select(
            "ingestion_runs", {"select": "*", "order": "started_at.desc", "limit": 1}
        )
        return IngestionRun.model_validate(rows[0]) if rows else None


def get_store(settings: Settings | None = None) -> Store:
    settings = settings or get_settings()
    if settings.store_backend == "supabase":
        logger.info("using Supabase store at %s", settings.supabase_url)
        return SupabaseStore(settings)
    logger.info("using file store at %s", settings.data_dir)
    return FileStore(settings.data_dir)
