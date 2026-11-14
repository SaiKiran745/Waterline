"""Human corrections (PATCH / DELETE /buildings/{id}/assets/{asset_id}) on the FIXTURE building.

Corrections and the agent memory store are redirected to a temporary folder, so real data is never touched.
"""
import pytest
from fastapi.testclient import TestClient

from app import buildings, corrections
from app.agent import memory
from app.main import app

client = TestClient(app, client=("127.0.0.1", 50000))
FIX = "fixture-1"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(corrections, "BUILDINGS", tmp_path / "buildings")
    monkeypatch.setattr(memory, "MEMORY_DB", tmp_path / "memory.sqlite")
    memory.store.cache_clear()
    yield
    memory.store.cache_clear()


def asset(aid: str) -> dict | None:
    return next((a for a in client.get(f"/buildings/{FIX}").json()["assets"] if a["id"] == aid), None)


def test_patch_height_is_saved_rescored_and_remembered():
    before = asset("fixture-1-a1")
    assert before["height_ft_high"] == 0.3
    hit_before = {h["asset_id"] for h in client.get(f"/buildings/{FIX}/scenario", params={"depth_ft": 1}).json()["assets_hit"]}
    assert "fixture-1-a1" in hit_before

    r = client.patch(f"/buildings/{FIX}/assets/fixture-1-a1", params={"depth_ft": 1},
                     json={"height_ft_low": 2.0, "height_ft_high": 2.5, "note": "tower sits on a shelf"})
    assert r.status_code == 200, r.text
    out = r.json()
    a = out["asset"]
    buildings.validate("asset", a)
    assert (a["height_ft_low"], a["height_ft_high"], a["confidence"], a["source"]) == (2.0, 2.5, 1.0, "human")
    assert "tower sits on a shelf" in a["evidence"]
    buildings.validate("scenario_result", out["scenario"])
    assert "fixture-1-a1" not in {h["asset_id"] for h in out["scenario"]["assets_hit"]}
    for m in out["mitigations"]:
        buildings.validate("mitigation", m)
    assert set(out["similar_asset_ids"]) >= {"fixture-1-a2", "fixture-1-a3"}     # the other desktop towers

    assert asset("fixture-1-a1")["height_ft_low"] == 2.0                         # applied on every read
    mem = memory.read_corrections(FIX)
    assert out["correction"]["id"] in mem and "height_ft_low 0.0 -> 2.0" in mem and "tower sits on a shelf" in mem


def test_delete_removes_asset_everywhere():
    r = client.request("DELETE", f"/buildings/{FIX}/assets/fixture-1-a4", json={"note": "not there any more"})
    assert r.status_code == 200, r.text
    assert r.json()["asset"] is None
    assert asset("fixture-1-a4") is None
    assert "fixture-1-a4" not in {h["asset_id"] for h in r.json()["scenario"]["assets_hit"]}
    assert "DELETED fixture-1-a4" in memory.read_corrections(FIX)


@pytest.mark.parametrize("body,code", [
    ({"height_ft_low": 3, "height_ft_high": 1}, 422),        # low above high
    ({"value_usd_high": 1}, 422),                             # not a correctable field
    ({"category": "spaceship"}, 422),                         # not in the contract enum
    ({}, 422),                                                # nothing to change
])
def test_bad_corrections_are_refused(body, code):
    r = client.patch(f"/buildings/{FIX}/assets/fixture-1-a1", json=body)
    assert r.status_code == code, r.text
    assert asset("fixture-1-a1")["height_ft_high"] == 0.3     # nothing saved


def test_unknown_asset_404():
    assert client.patch(f"/buildings/{FIX}/assets/nope", json={"label": "x"}).status_code == 404


def test_category_change_reprices_from_assumptions():
    r = client.patch(f"/buildings/{FIX}/assets/fixture-1-a4", json={"category": "finishes"})
    assert r.status_code == 200, r.text
    a = r.json()["asset"]
    assert (a["value_basis"], a["value_usd_low"], a["value_usd_high"]) == ("A-FIN", 0, 0)
