"""API behaviour on the fixture building, plus real buildings when the cache has them."""
import time

import pytest
from fastapi.testclient import TestClient

from app import buildings
from app.main import app

local = TestClient(app, client=("127.0.0.1", 50000))
remote = TestClient(app, client=("203.0.113.9", 50000))
FIX = "fixture-1"


def test_fixture_list_and_detail():
    assert [b["id"] for b in local.get("/buildings?fixture=1").json()] == [FIX]
    d = local.get(f"/buildings/{FIX}").json()
    assert set(d) == {"building", "entry_points", "assets"} and len(d["assets"]) == 25


def test_scenario_fast_and_valid():
    t = time.perf_counter()
    r = local.get(f"/buildings/{FIX}/scenario", params={"depth_ft": 2.75})
    assert r.status_code == 200 and (time.perf_counter() - t) < 0.1
    buildings.validate("scenario_result", r.json())
    assert local.get(f"/buildings/{FIX}/scenario", params={"depth_ft": 9}).status_code == 422


def test_mitigations_rerank_with_depth():
    at1 = local.get(f"/buildings/{FIX}/mitigations", params={"depth_ft": 1}).json()
    at4 = local.get(f"/buildings/{FIX}/mitigations", params={"depth_ft": 4}).json()
    for m in at1 + at4:
        buildings.validate("mitigation", m)
    assert at1[0]["kind"] == "entry_barrier" and at4[-1]["kind"] == "entry_barrier"


def test_sse_replay_streams_whole_trace():
    with local.stream("GET", f"/buildings/{FIX}/events", params={"speed": 0}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    assert body.count("event: agent_event") == 40 and "event: end" in body


def test_run_report_playbook():
    assert local.post(f"/buildings/{FIX}/run", json={"depth_ft": 4}).json()["status"] == "replay"
    assert "FIXTURE" in local.get(f"/buildings/{FIX}/report").text
    assert "FIXTURE" in local.get(f"/buildings/{FIX}/playbook").text


def test_send_requires_approval_and_allowed_recipient(monkeypatch):
    monkeypatch.setenv("ALLOWED_RECIPIENTS", "ops@example.com")
    assert local.post(f"/buildings/{FIX}/send", json={"approved": False, "recipient": "ops@example.com"}).status_code == 400
    assert local.post(f"/buildings/{FIX}/send", json={"approved": True, "recipient": "x@example.com"}).status_code == 403
    ok = local.post(f"/buildings/{FIX}/send", json={"approved": True, "recipient": "ops@example.com"}).json()
    assert ok["status"] == "not_sent"


def test_cors_allows_frontend_origin():
    r = local.get("/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
    r = local.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_media_local_only_and_no_traversal():
    assert remote.get("/media/anything.jpg").status_code == 403
    assert local.get("/media/../../.env").status_code == 404
    assert local.get("/media/%2e%2e/%2e%2e/.env").status_code == 404


def test_unknown_building_404():
    assert local.get("/buildings/does-not-exist").status_code == 404


@pytest.mark.skipif(not buildings.building_ids(), reason="no pulled buildings in data/cache")
def test_real_buildings_match_contract_and_media():
    listed = local.get("/buildings").json()
    assert listed
    for b in listed:
        buildings.validate("building", b)
        d = local.get(f"/buildings/{b['id']}").json()
        assert d["entry_points"] == [] and d["assets"] == []
        assert local.get(f"/media/{b['id']}/manifest.json").status_code == 200
    assert local.get(f"/buildings/{listed[0]['id']}/scenario", params={"depth_ft": 1}).status_code == 501
