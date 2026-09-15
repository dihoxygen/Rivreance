from __future__ import annotations

import httpx
import pytest

from lib.config import Settings
from lib.geo import Bbox
from lib.usgs import FabricClient, OgcFeaturesClient, UsgsApiError, WaterDataClient, chunked


def _feature(index: int) -> dict:
    return {"type": "Feature", "properties": {"id": f"USGS-{index:08d}"}, "geometry": None}


def _client(handler, settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_pagination_follows_offsets_until_a_short_page(settings):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        seen.append(params)
        offset = int(params["offset"])
        limit = int(params["limit"])
        remaining = max(0, 7 - offset)
        return httpx.Response(
            200, json={"features": [_feature(offset + i) for i in range(min(limit, remaining))]}
        )

    async with OgcFeaturesClient(
        "https://example.test/ogcapi", settings=settings, client=_client(handler, settings)
    ) as client:
        features = await client.fetch_items("monitoring-locations", page_size=3)

    assert len(features) == 7
    assert [params["offset"] for params in seen] == ["0", "3", "6"]
    assert all(params["f"] == "json" for params in seen)


async def test_sorted_queries_never_send_an_offset(settings):
    """The Water Data API rejects `offset` together with `sortby`."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"features": [_feature(i) for i in range(1000)]})

    async with WaterDataClient(settings=settings, client=_client(handler, settings)) as water:
        points = await water.continuous_series(
            "USGS-02461130",
            parameter_code="00060",
            start="2026-08-16T00:00:00Z",
            end="2026-09-15T00:00:00Z",
            max_points=1000,
        )

    assert len(points) == 1000
    assert len(captured) == 1
    params = captured[0].url.params
    assert "offset" not in params
    assert params["sortby"] == "-time"
    assert params["limit"] == "1000"


async def test_max_items_stops_early(settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"features": [_feature(i) for i in range(500)]})

    async with OgcFeaturesClient(
        "https://example.test/ogcapi", settings=settings, client=_client(handler, settings)
    ) as client:
        features = await client.fetch_items("continuous", page_size=500, max_items=10)

    assert len(features) == 10


async def test_api_key_is_sent_when_configured(settings):
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"features": []})

    async with OgcFeaturesClient(
        "https://example.test/ogcapi",
        settings=settings,
        client=_client(handler, settings),
        api_key="secret-key",
    ) as client:
        await client.get_json("collections/monitoring-locations/items")

    assert captured[0].url.params["api_key"] == "secret-key"


async def test_retryable_status_is_retried_then_succeeds(settings, monkeypatch):
    monkeypatch.setattr("lib.usgs.asyncio.sleep", _no_sleep)
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json={"features": [_feature(1)]})

    async with OgcFeaturesClient(
        "https://example.test/ogcapi", settings=settings, client=_client(handler, settings)
    ) as client:
        features = await client.fetch_items("daily", page_size=500)

    assert attempts["count"] == 3
    assert len(features) == 1


async def test_retries_are_exhausted_into_a_clear_error(settings, monkeypatch):
    monkeypatch.setattr("lib.usgs.asyncio.sleep", _no_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with OgcFeaturesClient(
        "https://example.test/ogcapi", settings=settings, client=_client(handler, settings)
    ) as client:
        with pytest.raises(UsgsApiError, match="failed after"):
            await client.get_json("collections/daily/items")


async def test_client_errors_are_not_retried(settings, monkeypatch):
    monkeypatch.setattr("lib.usgs.asyncio.sleep", _no_sleep)
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(400, json={"error": "bad filter"})

    async with OgcFeaturesClient(
        "https://example.test/ogcapi", settings=settings, client=_client(handler, settings)
    ) as client:
        with pytest.raises(UsgsApiError, match="HTTP 400"):
            await client.get_json("collections/daily/items")

    assert attempts["count"] == 1


async def test_latest_continuous_chunks_long_site_lists(settings):
    requested: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.params["monitoring_location_id"].split(","))
        return httpx.Response(200, json={"features": []})

    site_ids = [f"USGS-{index:08d}" for index in range(120)]
    async with WaterDataClient(settings=settings, client=_client(handler, settings)) as water:
        await water.latest_continuous(site_ids, parameter_codes=("00060", "00065"))

    assert [len(chunk) for chunk in requested] == [50, 50, 20]


async def test_flowline_requests_scope_to_the_basin_bbox_and_trim_properties(settings):
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"features": []})

    async with FabricClient(settings=settings, client=_client(handler, settings)) as fabric:
        await fabric.flowlines(Bbox(-87.7, 33.1, -86.7, 33.8))

    params = captured[0].url.params
    assert params["bbox"] == "-87.7,33.1,-86.7,33.8"
    assert "comid" in params["properties"] and "levelpathi" in params["properties"]


def test_chunked_covers_every_item():
    items = [str(index) for index in range(11)]
    chunks = list(chunked(items, 4))
    assert [len(chunk) for chunk in chunks] == [4, 4, 3]
    assert [item for chunk in chunks for item in chunk] == items


async def _no_sleep(_seconds: float) -> None:
    return None
