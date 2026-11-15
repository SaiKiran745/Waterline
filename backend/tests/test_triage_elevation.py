"""Contracts v1.3 elevation-aware triage: a common outside water level (FEMA's 1% level + offset) instead of a common
interior depth."""
import copy

import pytest
from fastapi.testclient import TestClient

from app import buildings, fixtures
from app.buildings import validate
from app.loss import grounding as ground
from app.loss import model, rank
from app.main import app

local = TestClient(app, client=("127.0.0.1", 50000))


def _g(floor, lo, hi, fema, f_lo, f_hi, dist=60, match=True):
    return {"datum": {"match": match}, "floor": {"elevation_ft": floor, "elevation_ft_low": lo, "elevation_ft_high": hi},
            "fema_1pct": {"found": True, "elevation_ft": fema, "elevation_ft_low": f_lo, "elevation_ft_high": f_hi,
                          "nearest_distance_m": dist}}


def _scen(d):
    v = round(1000 * d)
    return {"loss_usd_low": v, "loss_usd_median": v, "loss_usd_high": v, "structure_loss_usd_low": 0,
            "structure_loss_usd_median": 0, "structure_loss_usd_high": 0, "total_usd_low": v, "total_usd_median": v,
            "total_usd_high": v}


B_IN, B_OUT = {"in_mapped_flood_zone": True}, {"in_mapped_flood_zone": False}


def test_depth_is_water_level_minus_floor_never_below_zero():
    e = rank.elevation_entry(B_IN, _g(50.0, 48.0, 52.0, 51.0, 50.8, 51.2), 1, _scen)
    assert e["water_level_ft"] == 52.0 and e["interior_depth_ft"] == 2.0
    assert e["interior_depth_ft_low"] == pytest.approx(max(0, 51.8 - 52.0)) == 0.0     # low FEMA end over high floor end
    assert e["interior_depth_ft_high"] == pytest.approx(52.2 - 48.0)
    assert e["loss"]["total_median"] == 2000 and e["total_median_at_depth_range"] == [0, round(1000 * 4.2)]
    assert e["floor_above_fema_ft"] == -1.0 and e["sentence"] == "Floor is 1.0 ft below FEMA's 1% level."
    dry = rank.elevation_entry(B_OUT, _g(55.0, 53.0, 57.0, 51.0, 50.8, 51.2, dist=900), 0, _scen)
    assert dry["interior_depth_ft"] == 0.0 and dry["water_above_floor_ft"] == -4.0 and dry["loss"]["total_median"] == 0
    assert dry["sentence"] == "Floor is 4.0 ft above FEMA's 1% level (the nearest mapped level, 900 m away; a weak reference)."
    assert "no water inside" in dry["depth_sentence"]


def test_depth_capped_at_the_slider():
    e = rank.elevation_entry(B_IN, _g(40.0, 38.0, 42.0, 49.0, 48.0, 50.0), 3, _scen)
    assert e["interior_depth_ft"] == model.MAX_FT == e["interior_depth_ft_high"] and e["depth_capped"]
    assert "capped at the 8 ft slider" in e["depth_sentence"]


@pytest.mark.parametrize("g,why", [(None, "no elevation grounding yet"),
                                   ({"datum": {"match": True}, "fema_1pct": {"found": False}, "floor": {}}, "no FEMA 1% level found nearby"),
                                   (_g(50, 48, 52, 51, 50, 52, match=False), "FEMA and USGS datums differ")])
def test_missing_elevation_is_labelled(g, why):
    e = rank.elevation_entry(B_IN, g, 0, _scen)
    assert e["elevation"] == "missing" and e["missing_reason"] == why and e["interior_depth_ft"] is None and e["loss"] is None


def test_ranking_by_median_then_closest_floor_missing_last(monkeypatch):
    survey = {"status": "surveyed", "positions_read": 1, "scan_positions": 1, "contents_assets": 1, "note": "n"}
    entries = {"x-wet": rank.elevation_entry(B_IN, _g(50, 48, 52, 51, 50.8, 51.2), 0, _scen),
               "x-dry-close": rank.elevation_entry(B_OUT, _g(51.5, 49, 54, 51, 50.8, 51.2), 0, _scen),
               "x-dry-far": rank.elevation_entry(B_OUT, _g(56, 54, 58, 51, 50.8, 51.2), 0, _scen),
               "x-missing": rank.elevation_entry(B_IN, None, 0, _scen)}
    monkeypatch.setattr(rank, "load", lambda: {k: {"survey": survey, "fema": {"0": v}} for k, v in entries.items()})
    assert [r["building_id"] for r in rank.triage_elevation("0")] == ["x-wet", "x-dry-close", "x-dry-far", "x-missing"]
    assert [r["rank"] for r in rank.triage_elevation("0")] == [1, 2, 3, 4]


def test_real_buildings_all_have_elevation_and_offsets_only_raise_depth_and_loss():
    rows = {o: {r["building_id"]: r for r in rank.triage_elevation(str(o))} for o in rank.OFFSETS}
    if not rows[0]:
        pytest.skip("no ranking cached")
    for o in rank.OFFSETS:
        validate("triage_elevation", list(rows[o].values()))
    for bid in rows[0]:
        if ground.load(bid) is not None:
            assert rows[0][bid]["elevation"] == "ok", bid
        prev = None
        for o in rank.OFFSETS:
            r = rows[o][bid]
            if r["elevation"] != "ok":
                continue
            assert r["interior_depth_ft_low"] <= r["interior_depth_ft"] <= r["interior_depth_ft_high"]
            assert r["loss"]["total"][0] <= r["loss"]["total_median"] <= r["loss"]["total"][1]
            if prev:
                assert r["interior_depth_ft"] >= prev["interior_depth_ft"] and r["loss"]["total_median"] >= prev["loss"]["total_median"]
            prev = r
    medians = [r["loss"]["total_median"] for r in rank.triage_elevation("2") if r["elevation"] == "ok"]
    assert medians == sorted(medians, reverse=True)


def test_api_modes():
    r = local.get("/triage", params={"mode": "fema", "offset_ft": 2})
    if r.status_code == 503:
        pytest.skip("no ranking cached")
    validate("triage_elevation", r.json())
    assert local.get("/triage", params={"mode": "fema", "offset_ft": 5}).status_code == 422
    assert local.get("/triage", params={"mode": "flow"}).status_code == 422
    validate("triage", local.get("/triage", params={"depth_ft": 2}).json())          # same-depth mode unchanged
    fx = local.get("/triage", params={"mode": "fema", "offset_ft": 1, "fixture": 1}).json()
    validate("triage_elevation", fx)
    assert fx == fixtures.load("triage_elevation.json")
