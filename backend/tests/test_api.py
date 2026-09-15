from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from conftest import make_reading, make_segment, make_site
from fastapi.testclient import TestClient

from api.main import app, cache, get_store_dependency
from lib.models import (
    IngestionRun,
    ParameterSeries,
    SegmentCondition,
    SeriesPoint,
    SiteCondition,
    VelocityEstimate,
)
from lib.store import ConditionBundle, FileStore, ObservationBundle

NOW = datetime(2026, 9, 14, 12, tzinfo=UTC)


def _seed(store: FileStore) -> None:
    store.write_sites("03160112", [make_site()])
    store.write_segments(
        "03160112",
        [
            make_segment(comid=1, stream_order=4),
            make_segment(comid=2, stream_order=2, coordinates=[[[-87.2, 33.2], [-87.21, 33.21]]]),
        ],
    )
    store.write_observations(
        ObservationBundle(
            huc8="03160112",
            readings={"USGS-02462000": [make_reading("00060", 200.0, observed_at=NOW)]},
            series={
                "USGS-02462000": [
                    ParameterSeries(
                        parameter_code="00060",
                        unit="ft^3/s",
                        points=(SeriesPoint(time=NOW, value=200.0),),
                    )
                ]
            },
        )
    )
    store.write_conditions(
        ConditionBundle(
            huc8="03160112",
            activity="kayaking",
            site_conditions=[
                SiteCondition(
                    site_id="USGS-02462000",
                    activity="kayaking",
                    status="green",
                    color="#1a9850",
                    reason="200 is inside the optimal range",
                    discharge_cfs=200.0,
                    gage_height_ft=3.05,
                    observed_at=NOW,
                    trend="rising",
                    velocity=VelocityEstimate(
                        velocity_fps=1.8,
                        velocity_mph=1.227,
                        method="field_rating",
                        confidence="high",
                        area_sqft=111.0,
                    ),
                )
            ],
            segment_conditions=[
                SegmentCondition(
                    comid=1,
                    huc8="03160112",
                    activity="kayaking",
                    status="green",
                    color="#1a9850",
                    source_site_id="USGS-02462000",
                    assignment="mainstem",
                    distance_km=3.2,
                    reason="inside the optimal range",
                    computed_at=NOW,
                )
            ],
        )
    )
    store.write_run(
        IngestionRun(
            run_id="run-1",
            started_at=NOW - timedelta(minutes=6),
            finished_at=NOW - timedelta(minutes=5),
            status="success",
            basins=["03160112"],
            counts={"sites": 1, "segments": 2},
        )
    )


@pytest.fixture
def client(store: FileStore):
    _seed(store)
    cache.invalidate()
    app.dependency_overrides[get_store_dependency] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    cache.invalidate()


@pytest.fixture
def empty_client(store: FileStore):
    cache.invalidate()
    app.dependency_overrides[get_store_dependency] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    cache.invalidate()


def test_health_reports_the_last_run(client: TestClient):
    payload = client.get("/api/v1/health").json()
    assert payload["status"] == "ok"
    assert payload["last_run"]["run_id"] == "run-1"
    assert payload["store_backend"] == "file"
    assert payload["activities"] == ["kayaking", "fishing"]


def test_health_is_degraded_without_a_run(empty_client: TestClient):
    payload = empty_client.get("/api/v1/health").json()
    assert payload["status"] == "degraded"
    assert payload["stale"] is True
    assert payload["last_run"] is None


def test_basins_endpoint_lists_the_mvp_watersheds(client: TestClient):
    basins = client.get("/api/v1/basins").json()["basins"]
    assert [basin["huc8"] for basin in basins] == ["03160112", "03160113"]
    assert len(basins[0]["bbox"]) == 4


def test_segments_endpoint_returns_colored_geojson(client: TestClient):
    response = client.get("/api/v1/basins/03160112/segments", params={"activity": "kayaking"})
    payload = response.json()

    assert response.headers["cache-control"].startswith("public, max-age=")
    assert payload["type"] == "FeatureCollection"
    assert payload["activity"] == "kayaking"
    assert payload["status_counts"] == {"green": 1, "gray": 1}

    colored = next(f for f in payload["features"] if f["id"] == 1)
    assert colored["geometry"]["type"] == "MultiLineString"
    assert colored["properties"]["color"] == "#1a9850"
    assert colored["properties"]["assignment"] == "mainstem"
    assert colored["properties"]["line_width"] == 3.0

    uncolored = next(f for f in payload["features"] if f["id"] == 2)
    assert uncolored["properties"]["status"] == "gray"


def test_segments_endpoint_can_filter_small_streams(client: TestClient):
    payload = client.get(
        "/api/v1/basins/03160112/segments", params={"min_order": 4}
    ).json()
    assert [feature["id"] for feature in payload["features"]] == [1]


def test_segments_endpoint_rejects_unknown_basins_and_activities(client: TestClient):
    assert client.get("/api/v1/basins/99999999/segments").status_code == 404
    assert client.get(
        "/api/v1/basins/03160112/segments", params={"activity": "surfing"}
    ).status_code == 422


def test_sites_endpoint_exposes_condition_and_velocity(client: TestClient):
    payload = client.get("/api/v1/basins/03160112/sites").json()
    properties = payload["features"][0]["properties"]

    assert payload["status_counts"] == {"green": 1}
    assert properties["site_id"] == "USGS-02462000"
    assert properties["discharge_cfs"] == 200.0
    assert properties["velocity_mph"] == pytest.approx(1.23, abs=0.01)
    assert properties["velocity_method"] == "field_rating"
    assert properties["trend"] == "rising"
    assert properties["available_parameters"] == ["00060"]


def test_sites_endpoint_falls_back_to_gray_without_conditions(empty_client: TestClient, store):
    store.write_sites("03160112", [make_site()])
    payload = empty_client.get("/api/v1/basins/03160112/sites").json()
    assert payload["features"][0]["properties"]["status"] == "gray"


def test_series_endpoint_returns_cached_points(client: TestClient):
    payload = client.get("/api/v1/sites/USGS-02462000/series", params={"parameter": "00060"}).json()
    assert payload["unit"] == "ft^3/s"
    assert payload["points"][0]["value"] == 200.0


def test_series_endpoint_404s_for_unknown_parameters(client: TestClient):
    response = client.get("/api/v1/sites/USGS-02462000/series", params={"parameter": "00065"})
    assert response.status_code == 404


def test_responses_are_cached_so_the_store_is_read_once(client: TestClient, store: FileStore):
    reads = {"count": 0}
    original = store.read_segments

    def counting_read(huc8: str):
        reads["count"] += 1
        return original(huc8)

    store.read_segments = counting_read  # type: ignore[method-assign]
    client.get("/api/v1/basins/03160112/segments")
    client.get("/api/v1/basins/03160112/segments")

    assert reads["count"] == 1
