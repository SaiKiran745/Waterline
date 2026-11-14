"""API behaviour on the fixture building, plus real buildings when the cache has them."""
import re
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


def test_unscreened_panorama_faces_are_refused():
    idx = buildings.building_ids()
    if not idx:
        return
    bid = sorted(idx)[0]
    man = local.get(f"/buildings/{bid}/media").json()
    import json
    from app.config import BUILDINGS
    pano = json.loads((BUILDINGS / bid / "media_index.json").read_text())["panos"][0]
    scr = json.loads((BUILDINGS / bid / "screening.json").read_text()) if (BUILDINGS / bid / "screening.json").exists() else {}
    if not scr.get(f"{pano['id']}/face1", {}).get("clear"):
        assert local.get(pano["faces"][1]).status_code == 403


def test_mitigations_rerank_with_depth():
    at1 = local.get(f"/buildings/{FIX}/mitigations", params={"depth_ft": 1}).json()
    at4 = local.get(f"/buildings/{FIX}/mitigations", params={"depth_ft": 4}).json()
    for m in at1 + at4:
        buildings.validate("mitigation", m)
    assert at1[0]["kind"] == "entry_barrier"
    bar4 = next(m for m in at4 if m["kind"] == "entry_barrier")
    assert bar4["avoided_loss_usd_high"] == 0 and all(bar4["rank"] > m["rank"] for m in at4 if m["avoided_loss_usd_high"] > 0)
    assert sorted(m["id"] for m in at1) == sorted(m["id"] for m in at4)   # stable ids across depths
    assert {m["depth_ft"] for m in local.get(f"/buildings/{FIX}/mitigations", params={"depth_ft": 3.3}).json()} == {3.3}


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
        assert local.get(f"/media/{b['id']}/mesh/mesh_50k.obj").status_code == 200
    bid = listed[0]["id"]
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", bid) and "costar_property_id" not in listed[0]
    buildings.validate("scenario_result", local.get(f"/buildings/{bid}/scenario", params={"depth_ft": 1.5}).json())
    for m in local.get(f"/buildings/{bid}/mitigations", params={"depth_ft": 3.3}).json():
        buildings.validate("mitigation", m)
    for path in ("report", "playbook"):
        assert local.get(f"/buildings/{bid}/{path}").status_code == 200
    man = local.get(f"/buildings/{bid}/media").json()
    assert "ortho" in man["aerial"] and man["mesh"]["url"].startswith(f"/media/{bid}/")
