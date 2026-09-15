"""Thin async clients for the USGS OGC APIs.

Two services are used:

* **USGS Water Data OGC API** (`api.waterdata.usgs.gov/ogcapi/v0`) — gage metadata
  and observations. The legacy WaterServices endpoints are deliberately not used.
* **USGS National Hydrologic Geospatial Fabric** (`api.water.usgs.gov/fabric/pygeoapi`)
  — NHDPlus v2 flowlines and Watershed Boundary Dataset polygons.

Both are OGC API Features services, so one small pagination helper covers them.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable, Sequence
from typing import Any

import httpx

from lib.config import Settings, get_settings
from lib.geo import Bbox

logger = logging.getLogger(__name__)

Feature = dict[str, Any]

_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

FLOWLINE_PROPERTIES = (
    "comid",
    "reachcode",
    "gnis_name",
    "streamorde",
    "lengthkm",
    "slope",
    "levelpathi",
    "pathlength",
    "totdasqkm",
    "qe_ma",
    "ve_ma",
)


class UsgsApiError(RuntimeError):
    """Raised when a USGS service keeps failing after all retries."""


class OgcFeaturesClient:
    """Paginating OGC API Features client with retry/backoff and a concurrency cap."""

    def __init__(
        self,
        base_url: str,
        *,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(self._settings.request_timeout_seconds),
            headers={"Accept": "application/json", "User-Agent": "rivreance/0.1 (+etl)"},
            follow_redirects=True,
        )
        self._semaphore = asyncio.Semaphore(self._settings.max_concurrent_requests)

    async def __aenter__(self) -> OgcFeaturesClient:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query: dict[str, Any] = {"f": "json"}
        query.update({k: v for k, v in (params or {}).items() if v is not None})
        if self._api_key:
            query["api_key"] = self._api_key

        url = f"{self._base_url}/{path.lstrip('/')}"
        last_error: Exception | None = None
        for attempt in range(self._settings.max_retries):
            try:
                async with self._semaphore:
                    response = await self._client.get(url, params=query)
                if response.status_code in _RETRYABLE_STATUS:
                    raise httpx.HTTPStatusError(
                        f"retryable status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and status not in _RETRYABLE_STATUS:
                    raise UsgsApiError(f"{url} failed with HTTP {status}") from exc
                last_error = exc
                backoff = 2**attempt
                logger.warning(
                    "USGS request failed (attempt %s/%s): %s — retrying in %ss",
                    attempt + 1,
                    self._settings.max_retries,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
        raise UsgsApiError(f"{url} failed after {self._settings.max_retries} attempts") from last_error

    async def iter_items(
        self,
        collection: str,
        *,
        params: dict[str, Any] | None = None,
        page_size: int = 500,
        max_items: int | None = None,
    ) -> AsyncIterator[Feature]:
        """Yield features from a collection, following offset pagination."""
        offset = 0
        yielded = 0
        while True:
            page_params = dict(params or {})
            page_params.update({"limit": page_size, "offset": offset})
            payload = await self.get_json(f"collections/{collection}/items", page_params)
            features = payload.get("features") or []
            for feature in features:
                yield feature
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return
            if len(features) < page_size:
                return
            offset += page_size

    async def fetch_items(
        self,
        collection: str,
        *,
        params: dict[str, Any] | None = None,
        page_size: int = 500,
        max_items: int | None = None,
    ) -> list[Feature]:
        return [
            feature
            async for feature in self.iter_items(
                collection, params=params, page_size=page_size, max_items=max_items
            )
        ]

    async def fetch_sorted_page(
        self, collection: str, *, params: dict[str, Any], limit: int
    ) -> list[Feature]:
        """Fetch one page of a sorted query.

        The Water Data API rejects `offset` whenever `sortby` is present ("Only the
        first page of data can be returned when specifying 'sortby'"), so sorted
        queries ask for everything they need in a single request instead of paging.
        """
        payload = await self.get_json(
            f"collections/{collection}/items", {**params, "limit": limit}
        )
        return payload.get("features") or []


def chunked(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class WaterDataClient:
    """Gage metadata and observations from the USGS Water Data OGC API."""

    #: The service accepts comma-separated ids; keep URLs comfortably short.
    SITE_CHUNK_SIZE = 50

    def __init__(self, *, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self._settings = settings or get_settings()
        self._ogc = OgcFeaturesClient(
            self._settings.usgs_ogc_base_url,
            settings=self._settings,
            client=client,
            api_key=self._settings.usgs_api_key,
        )

    async def __aenter__(self) -> WaterDataClient:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._ogc.aclose()

    async def monitoring_locations(
        self, *, huc: str, site_type_code: str = "ST"
    ) -> list[Feature]:
        """Sites in a hydrologic unit. `huc` may be any HUC prefix (e.g. a HUC-8)."""
        return await self._ogc.fetch_items(
            "monitoring-locations",
            params={"hydrologic_unit_code": huc, "site_type_code": site_type_code},
            page_size=1000,
        )

    async def latest_continuous(
        self, site_ids: Sequence[str], *, parameter_codes: Sequence[str]
    ) -> list[Feature]:
        """Newest sensor reading per (site, parameter, statistic)."""
        features: list[Feature] = []
        for chunk in chunked(site_ids, self.SITE_CHUNK_SIZE):
            features.extend(
                await self._ogc.fetch_items(
                    "latest-continuous",
                    params={
                        "monitoring_location_id": ",".join(chunk),
                        "parameter_code": ",".join(parameter_codes),
                    },
                    page_size=2000,
                )
            )
        return features

    async def continuous_series(
        self, site_id: str, *, parameter_code: str, start: str, end: str, max_points: int = 1000
    ) -> list[Feature]:
        """Instantaneous values for one site/parameter over a time window."""
        return await self._ogc.fetch_sorted_page(
            "continuous",
            params={
                "monitoring_location_id": site_id,
                "parameter_code": parameter_code,
                "datetime": f"{start}/{end}",
                "sortby": "-time",
            },
            limit=max_points,
        )

    async def daily_values(
        self,
        site_id: str,
        *,
        parameter_code: str,
        start: str,
        end: str,
        statistic_id: str = "00003",
        max_points: int = 400,
    ) -> list[Feature]:
        """Daily statistics (default: mean) used for percentile classification."""
        return await self._ogc.fetch_sorted_page(
            "daily",
            params={
                "monitoring_location_id": site_id,
                "parameter_code": parameter_code,
                "statistic_id": statistic_id,
                "datetime": f"{start}/{end}",
                "sortby": "-time",
            },
            limit=max_points,
        )

    async def channel_measurements(self, site_id: str, *, max_points: int = 200) -> list[Feature]:
        """Discrete field measurements with paired discharge, area, width, and velocity."""
        return await self._ogc.fetch_sorted_page(
            "channel-measurements",
            params={"monitoring_location_id": site_id, "sortby": "-time"},
            limit=max_points,
        )

    async def field_measurements(self, site_ids: Sequence[str], *, max_points: int = 200) -> list[Feature]:
        """Latest discrete samples, shown as a separate map layer."""
        features: list[Feature] = []
        for chunk in chunked(site_ids, self.SITE_CHUNK_SIZE):
            features.extend(
                await self._ogc.fetch_items(
                    "latest-field-measurements",
                    params={"monitoring_location_id": ",".join(chunk)},
                    page_size=500,
                    max_items=max_points,
                )
            )
        return features


class FabricClient:
    """NHDPlus flowlines and WBD basin polygons from the USGS geospatial Fabric."""

    WBD_HUC8_COLLECTION = "wbd08_20250107"
    FLOWLINE_COLLECTION = "nhdflowline_network"

    def __init__(self, *, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self._settings = settings or get_settings()
        self._ogc = OgcFeaturesClient(
            self._settings.usgs_fabric_base_url, settings=self._settings, client=client
        )

    async def __aenter__(self) -> FabricClient:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._ogc.aclose()

    async def huc8_boundary(self, huc8: str) -> Feature | None:
        features = await self._ogc.fetch_items(
            self.WBD_HUC8_COLLECTION, params={"huc8": huc8}, page_size=5, max_items=1
        )
        return features[0] if features else None

    async def flowlines(self, bbox: Bbox, *, page_size: int = 500) -> list[Feature]:
        """Flowlines intersecting a bbox, with only the attributes the pipeline needs."""
        return await self._ogc.fetch_items(
            self.FLOWLINE_COLLECTION,
            params={"bbox": bbox.as_param(), "properties": ",".join(FLOWLINE_PROPERTIES)},
            page_size=page_size,
        )
