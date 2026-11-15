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


def test_send_requires_approval_and_allowed_recipient(monkeypatch, tmp_path):
    from app.actions import send as send_action
    monkeypatch.setattr(send_action, "LOG_DIR", tmp_path)
    monkeypatch.setenv("ALLOWED_RECIPIENTS", "ops@example.com")
    for k in send_action.SETTINGS:
        monkeypatch.delenv(k, raising=False)
    assert local.post(f"/buildings/{FIX}/send", json={"approved": False, "recipient": "ops@example.com"}).status_code == 400
    assert local.post(f"/buildings/{FIX}/send", json={"approved": True, "recipient": "x@example.com"}).status_code == 403
    ok = local.post(f"/buildings/{FIX}/send", json={"approved": True, "recipient": "ops@example.com"}).json()
    assert ok["status"] == "draft_only" and ok["detail"].startswith("draft only, not sent")


def test_send_over_smtp_when_configured(monkeypatch, tmp_path):
    from app.actions import send as send_action
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent.append(("connect", host, port))
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starttls(self, context=None):
            sent.append(("starttls",))
        def login(self, user, password):
            sent.append(("login", user))
        def send_message(self, msg):
            sent.append(("send", msg["To"], msg["Subject"]))
    monkeypatch.setattr(send_action.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(send_action, "LOG_DIR", tmp_path)
    monkeypatch.setenv("ALLOWED_RECIPIENTS", "ops@example.com")
    for k, v in {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587", "SMTP_USER": "u", "SMTP_PASSWORD": "p",
                 "EMAIL_FROM": "waterline@example.com"}.items():
        monkeypatch.setenv(k, v)
    out = send_action.send_playbook(FIX, "ops@example.com", 4, "<p>playbook</p>", approved=True)
    assert out["status"] == "sent" and ("send", "ops@example.com", "Waterline pre-storm playbook (4 ft scenario)") in sent
    assert send_action.send_playbook(FIX, "x@example.com", 4, "", approved=True)["status"] == "refused"
    assert send_action.send_playbook(FIX, "ops@example.com", 4, "", approved=False)["status"] == "refused"
    log = (tmp_path / FIX / "sends.json").read_text()
    assert "SMTP_PASSWORD" not in log and '"p"' not in log


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
        for kind, rows in (("entry_point", d["entry_points"]), ("asset", d["assets"])):
            for row in rows:
                buildings.validate(kind, row)
                assert row["building_id"] == b["id"]
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


@pytest.mark.skipif(not buildings.building_ids(), reason="no pulled buildings in data/cache")
def test_agent_routes_guard_their_order():
    bid = sorted(buildings.building_ids())[0]
    assert local.post(f"/buildings/{bid}/depth", json={"depth_ft": 4}).status_code in (403, 409)
    st = local.get(f"/buildings/{bid}/agent").json()
    assert st["building_id"] == bid
    assert local.get("/buildings/fixture-1/events", params={"speed": 0}).status_code == 200


def test_approve_without_recipient_uses_the_first_allowed_address(monkeypatch, tmp_path):
    from app.actions import send as send_action
    monkeypatch.setattr(send_action, "LOG_DIR", tmp_path)
    monkeypatch.setenv("ALLOWED_RECIPIENTS", "ops@example.com, other@example.com")
    for k in send_action.SETTINGS:
        monkeypatch.delenv(k, raising=False)
    r = local.post("/buildings/fixture-1/send", json={"approved": True})
    assert r.status_code == 200 and r.json()["recipient"] == "ops@example.com"
    assert local.post("/buildings/fixture-1/send", json={"approved": True, "recipient": "x@evil.test"}).status_code == 403


def test_demo_reset_is_localhost_only():
    assert remote.post("/demo/reset").status_code == 403


def test_agent_status_reports_memory_and_last_delivery(monkeypatch, tmp_path):
    """GET /agent: active human corrections, corrections the agent applied this session, and the last send."""
    import json
    from types import SimpleNamespace

    from app import buildings, corrections
    from app.actions import send as send_action
    from app.agent import service
    bid = "building-e"
    if bid not in buildings.building_ids():
        pytest.skip("building-e not pulled")
    path = tmp_path / "corrections.json"
    monkeypatch.setattr(corrections, "_path", lambda b: path)
    monkeypatch.setattr(send_action, "LOG_DIR", tmp_path)
    monkeypatch.setenv("ALLOWED_RECIPIENTS", "ops@example.com")
    for k in send_action.SETTINGS:
        monkeypatch.delenv(k, raising=False)
    rec = lambda i, by, ts, **kw: {"id": i, "asset_id": f"{bid}-a{i[-1]}", "action": "patch", "by": by, "ts": ts,
                                   "changes": {"height_ft_low": 1.5}, "note": "steel desks", **kw}
    path.write_text(json.dumps([
        rec("corr-h1", "human", "2026-11-14T10:00:00+00:00"),
        rec("corr-a2", "agent", "2026-11-14T11:59:00+00:00"),                       # before this session
        rec("corr-a3", "agent", "2026-11-14T12:05:00+00:00"),                       # in this session
        rec("corr-h4", "human", "2026-11-14T09:00:00+00:00", inactive={"reason": "x"})]))

    s = local.get(f"/buildings/{bid}/agent").json()
    assert s["session"] is None and s["last_delivery"] is None
    assert s["memory"]["active_human_corrections"] == 1 and s["memory"]["applied_this_session"] == 0
    assert [c["id"] for c in s["memory"]["human_corrections"]] == ["corr-h1"]

    fake = SimpleNamespace(run_id="r1", started_at="2026-11-14T12:00:00+00:00", turns=[], trace=SimpleNamespace(events=[]))
    monkeypatch.setitem(service._sessions, bid, fake)
    send_action.send_playbook(bid, "ops@example.com", 4, "<p>x</p>", approved=True)
    s = local.get(f"/buildings/{bid}/agent").json()
    assert s["memory"]["applied_this_session"] == 1 and s["memory"]["applied_this_session_asset_ids"] == [f"{bid}-a3"]
    d = s["last_delivery"]
    assert d["status"] == "draft_only" and d["recipient"] == "ops@example.com" and d["at"] and d["detail"]


def test_grounding_endpoint():
    r = local.get(f"/buildings/{FIX}/grounding")
    assert r.status_code == 200
    buildings.validate("grounding", r.json())
    from app.loss import grounding as ground
    for bid in sorted(buildings.building_ids()):
        r = local.get(f"/buildings/{bid}/grounding")
        if ground.load(bid) is None:
            assert r.status_code == 503
            continue
        g = r.json()
        buildings.validate("grounding", g)
        assert "samples" not in g and len(g["steps"]) == 33


def test_real_scenario_under_100ms_warm():
    bid = "building-e"
    if bid not in buildings.building_ids():
        pytest.skip("no cached building")
    local.get(f"/buildings/{bid}/scenario", params={"depth_ft": 2})
    t = time.perf_counter()
    r = local.get(f"/buildings/{bid}/scenario", params={"depth_ft": 2.5})
    assert r.status_code == 200 and (time.perf_counter() - t) < 0.1
    buildings.validate("scenario_result", r.json())
