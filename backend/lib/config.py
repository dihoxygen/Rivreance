"""Runtime configuration for the Rivreance ETL and API.

Every value can be overridden with an environment variable (see `.env.example`).
Secrets (`USGS_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`) are read here so they stay
server-side; nothing in this module is ever shipped to the browser.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
CONFIG_DIR = BACKEND_ROOT / "config"

Activity = Literal["kayaking", "fishing"]
ACTIVITIES: tuple[Activity, ...] = ("kayaking", "fishing")

DISCHARGE_PARAMETER = "00060"
GAGE_HEIGHT_PARAMETER = "00065"


class Settings(BaseSettings):
    """Environment-driven settings shared by the ETL scripts and the API."""

    model_config = SettingsConfigDict(
        env_prefix="RIVREANCE_",
        env_file=(REPO_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- USGS services (modern OGC API only; legacy WaterServices retires ~Q1 2027) ---
    usgs_ogc_base_url: str = "https://api.waterdata.usgs.gov/ogcapi/v0"
    usgs_fabric_base_url: str = "https://api.water.usgs.gov/fabric/pygeoapi"
    usgs_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RIVREANCE_USGS_API_KEY", "USGS_API_KEY"),
    )
    request_timeout_seconds: float = 60.0
    max_retries: int = 4
    max_concurrent_requests: int = 4

    # --- Storage ---
    store_backend: Literal["file", "supabase"] = "file"
    data_dir: Path = BACKEND_ROOT / ".data"
    supabase_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RIVREANCE_SUPABASE_URL", "SUPABASE_URL"),
    )
    supabase_service_role_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "RIVREANCE_SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_ROLE_KEY"
        ),
    )

    # --- Pipeline behaviour ---
    #: Continuous readings older than this are treated as unknown (gray).
    stale_after_minutes: int = 120
    #: Gages whose newest reading predates this window are skipped entirely.
    inactive_after_days: int = 30
    #: Snap distance when matching a gage to its NHD flowline.
    gage_snap_distance_m: float = 750.0
    #: Fallback radius when a segment shares no mainstem with any gage.
    proximity_assign_distance_km: float = 5.0
    #: Cap on along-mainstem distance between a segment and its source gage.
    mainstem_assign_distance_km: float = 60.0
    #: Only ingest flowlines at or above this Strahler order (keeps the basin tractable).
    min_stream_order: int = 3
    #: Days of daily-values history used for percentile classification.
    history_days: int = 30
    #: Cap on instantaneous values sampled when a gage publishes no daily record.
    history_sample_limit: int = 5000
    #: Hours of instantaneous history cached for popup trend charts.
    series_hours: int = 24

    # --- API ---
    cache_ttl_seconds: int = 900  # 15 minutes, per USGS courtesy guidance
    cors_allow_origins: str = "http://localhost:3000"
    default_activity: Activity = "kayaking"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


class BasinConfig(BaseModel):
    """A HUC-8 watershed the MVP ingests."""

    huc8: str
    name: str
    #: [west, south, east, north] in WGS84, taken from the USGS WBD polygon.
    bbox: tuple[float, float, float, float]
    center: tuple[float, float]
    default_zoom: float = 9.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def load_basins() -> tuple[BasinConfig, ...]:
    payload = json.loads((CONFIG_DIR / "basins.json").read_text(encoding="utf-8"))
    return tuple(BasinConfig.model_validate(item) for item in payload["basins"])


def get_basin(huc8: str) -> BasinConfig | None:
    return next((basin for basin in load_basins() if basin.huc8 == huc8), None)
