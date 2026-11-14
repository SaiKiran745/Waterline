"""DEMO_MODE=1 runs the demo path from cache with the network off; "Replay last run" is labelled as a replay."""
import json
import socket

import pytest
from fastapi.testclient import TestClient

from app import buildings
from app.agent import replay as replay_mod

BID = "building-e"
pytestmark = pytest.mark.skipif(BID not in buildings.building_ids(), reason="building-e not pulled")


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """DEMO_MODE=1 and no network: any socket connection or DNS lookup fails the test."""
    def refuse(*a, **k):
        raise AssertionError(f"network used in DEMO_MODE: {a[1:2]}")
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    from app.actions import send
    monkeypatch.setattr(send, "LOG_DIR", tmp_path)
    monkeypatch.setenv("ALLOWED_RECIPIENTS", "ops@example.com")
    for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM"):
        monkeypatch.setenv(k, "set-but-unused")
    from app.main import app
    return TestClient(app, client=("127.0.0.1", 50000))      # /media is served to localhost only


def test_demo_path_runs_from_cache_with_network_off(offline):
    c = offline
    assert c.get("/health").json()["demo_mode"] is True
    assert len(c.get("/buildings").json()) >= 6
    tri = c.get("/triage?depth_ft=2").json()
    assert all(r["positions_read"] <= r["scan_positions"] for r in tri)
    d = c.get(f"/buildings/{BID}").json()
    assert d["entry_points"] and d["assets"]
    m = c.get(f"/buildings/{BID}/media").json()
    mesh = next(v for k, v in m.items() if "mesh" in k)
    url = mesh if isinstance(mesh, str) else (mesh.get("url") or mesh.get("obj"))
    if url:
        assert c.get(url).status_code == 200
    for depth in (1, 4):
        assert c.get(f"/buildings/{BID}/scenario?depth_ft={depth}").status_code == 200
        assert c.get(f"/buildings/{BID}/mitigations?depth_ft={depth}").status_code == 200
    assert c.get(f"/buildings/{BID}/scenario_table").status_code == 200
    assert "$" in c.get(f"/buildings/{BID}/report?depth_ft=4").text
    assert c.get(f"/buildings/{BID}/playbook?depth_ft=4").status_code == 200
    sent = c.post(f"/buildings/{BID}/send?depth_ft=4", json={"approved": True, "recipient": "ops@example.com"}).json()
    assert sent["status"] == "draft_only" and "DEMO_MODE" in sent["detail"]      # SMTP set, but no network


def test_replay_last_run_is_labelled(offline):
    if replay_mod.last_run(BID) is None:
        pytest.skip("no saved agent run for building-e")
    r = offline.post(f"/buildings/{BID}/run", json={"depth_ft": 1}).json()        # demo mode: replay, not live
    assert r["status"] == "replay" and r["label"].startswith("REPLAY") and r["events_url"].endswith("replay=1")
    body = offline.get(f"/buildings/{BID}/events?replay=1&speed=0").text
    blocks = [b for b in body.split("\n\n") if b.strip()]
    assert blocks[0].startswith("event: replay")
    end = json.loads(blocks[-1].split("data: ", 1)[1])
    assert end["replay"] is True and end["events"] == r["events"]
