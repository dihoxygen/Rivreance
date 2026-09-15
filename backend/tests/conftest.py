from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from lib.config import Settings  # noqa: E402
from lib.models import MonitoringSite, Reading, RiverSegment  # noqa: E402
from lib.store import FileStore  # noqa: E402

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", store_backend="file")


@pytest.fixture
def store(settings: Settings) -> FileStore:
    return FileStore(settings.data_dir)


@pytest.fixture
def now() -> datetime:
    return NOW


def make_site(
    site_id: str = "USGS-02462000",
    *,
    latitude: float = 33.35,
    longitude: float = -87.05,
    levelpath_id: float | None = 290048945.0,
    path_length_km: float | None = 620.0,
    segment_drainage_sqkm: float | None = 100.0,
    comid: int | None = 18226803,
    name: str = "Valley Creek Near Oak Grove, Al",
) -> MonitoringSite:
    return MonitoringSite(
        site_id=site_id,
        site_number=site_id.split("-")[-1],
        name=name,
        latitude=latitude,
        longitude=longitude,
        huc8="03160112",
        comid=comid,
        levelpath_id=levelpath_id,
        path_length_km=path_length_km,
        segment_drainage_sqkm=segment_drainage_sqkm,
        snap_distance_m=25.0 if comid is not None else None,
    )


def make_segment(
    comid: int = 18226803,
    *,
    levelpath_id: float | None = 290048945.0,
    path_length_km: float | None = 620.0,
    drainage_sqkm: float | None = 100.0,
    coordinates: list[list[list[float]]] | None = None,
    stream_order: int | None = 4,
) -> RiverSegment:
    return RiverSegment(
        comid=comid,
        huc8="03160112",
        name="Valley Creek",
        reach_code="03160112000597",
        stream_order=stream_order,
        length_km=1.2,
        levelpath_id=levelpath_id,
        path_length_km=path_length_km,
        drainage_sqkm=drainage_sqkm,
        erom_flow_cfs=90.0,
        erom_velocity_fps=1.2,
        geometry=coordinates or [[[-87.05, 33.35], [-87.04, 33.36]]],
    )


def make_reading(
    parameter_code: str = "00060",
    value: float = 200.0,
    *,
    observed_at: datetime | None = None,
    unit: str = "ft^3/s",
) -> Reading:
    return Reading(
        parameter_code=parameter_code,
        value=value,
        unit=unit,
        observed_at=observed_at or NOW,
    )
