from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from conftest import make_reading, make_segment, make_site

from lib.config import Settings
from lib.models import IngestionRun, ParameterSeries, SeriesPoint, SiteCondition
from lib.store import (
    ConditionBundle,
    FileStore,
    ObservationBundle,
    SupabaseStore,
    _multiline_to_ewkt,
    get_store,
)


def test_file_store_round_trips_sites_and_segments(store: FileStore):
    store.write_sites("03160112", [make_site()])
    store.write_segments("03160112", [make_segment()])

    assert store.read_sites("03160112")[0].site_id == "USGS-02462000"
    assert store.read_segments("03160112")[0].comid == 18226803
    assert store.read_sites("03160113") == []  # unknown basin reads empty, not an error


def test_file_store_round_trips_observations(store: FileStore):
    bundle = ObservationBundle(
        huc8="03160112",
        readings={"USGS-02462000": [make_reading()]},
        series={
            "USGS-02462000": [
                ParameterSeries(
                    parameter_code="00060",
                    unit="ft^3/s",
                    points=(SeriesPoint(time=datetime(2026, 9, 14, tzinfo=UTC), value=1.0),),
                )
            ]
        },
    )
    store.write_observations(bundle)

    restored = store.read_observations("03160112")
    assert restored.readings["USGS-02462000"][0].value == 200.0
    assert restored.series["USGS-02462000"][0].points[0].value == 1.0


def test_file_store_writes_are_atomic_and_leave_no_temp_files(store: FileStore):
    store.write_sites("03160112", [make_site()])
    files = sorted(path.name for path in (store.data_dir / "03160112").iterdir())
    assert files == ["sites.json"]


def test_file_store_keeps_the_newest_run(store: FileStore):
    older = IngestionRun(run_id="a", started_at=datetime(2026, 9, 14, 10, tzinfo=UTC))
    newer = IngestionRun(run_id="b", started_at=datetime(2026, 9, 14, 11, tzinfo=UTC))
    store.write_run(older)
    store.write_run(newer)

    latest = store.read_latest_run()
    assert latest is not None and latest.run_id == "b"


def test_file_store_updates_a_run_in_place(store: FileStore):
    run = IngestionRun(run_id="a", started_at=datetime(2026, 9, 14, 10, tzinfo=UTC))
    store.write_run(run)
    store.write_run(run.model_copy(update={"status": "success", "counts": {"sites": 3}}))

    history = json.loads((store.data_dir / "runs.json").read_text())
    assert len(history) == 1
    assert history[0]["status"] == "success"


def test_conditions_are_stored_per_activity(store: FileStore):
    for activity, status in (("kayaking", "red"), ("fishing", "green")):
        store.write_conditions(
            ConditionBundle(
                huc8="03160112",
                activity=activity,
                site_conditions=[
                    SiteCondition(
                        site_id="USGS-02462000",
                        activity=activity,
                        status=status,
                        color="#000000",
                        reason="test",
                    )
                ],
            )
        )

    assert store.read_conditions("03160112", "kayaking").site_conditions[0].status == "red"
    assert store.read_conditions("03160112", "fishing").site_conditions[0].status == "green"


def test_get_store_defaults_to_the_file_backend(settings: Settings):
    assert isinstance(get_store(settings), FileStore)


def test_supabase_store_requires_credentials():
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        SupabaseStore(Settings(store_backend="supabase", supabase_url=None))


def test_multiline_to_ewkt_declares_srid_4326():
    wkt = _multiline_to_ewkt([[[-87.0, 33.0], [-87.01, 33.01]]])
    assert wkt == "SRID=4326;MULTILINESTRING((-87.0 33.0,-87.01 33.01))"


def _supabase_store(handler) -> tuple[SupabaseStore, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    settings = Settings(
        store_backend="supabase",
        supabase_url="https://project.supabase.co",
        supabase_service_role_key="service-role-key",
    )
    client = httpx.Client(
        transport=httpx.MockTransport(recording_handler),
        base_url="https://project.supabase.co/rest/v1",
        headers={"apikey": "service-role-key", "Authorization": "Bearer service-role-key"},
    )
    return SupabaseStore(settings, client=client), requests


def test_supabase_store_upserts_segments_as_ewkt_geometry():
    store, requests = _supabase_store(lambda request: httpx.Response(201, json=[]))

    store.write_segments("03160112", [make_segment()])

    assert len(requests) == 1
    request = requests[0]
    assert request.url.path.endswith("/river_segments")
    assert request.url.params["on_conflict"] == "comid"
    assert "merge-duplicates" in request.headers["Prefer"]
    row = json.loads(request.content)[0]
    assert row["geom"].startswith("SRID=4326;MULTILINESTRING")
    assert "geometry" not in row


def test_supabase_store_reads_segments_from_the_geojson_view():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v_river_segments")
        assert request.url.params["huc8"] == "eq.03160112"
        return httpx.Response(200, json=[make_segment().model_dump(mode="json")])

    store, _requests = _supabase_store(handler)
    assert store.read_segments("03160112")[0].comid == 18226803
