"""Contracts v1.3 grounding (judge feedback part B): the slider depth tied to real elevations, no flow model."""
import copy

import pytest

from app import fixtures
from app.buildings import validate
from app.loss import grounding as ground


def _inputs():
    g = fixtures.grounding()        # built through ground.assemble from FIXTURE points
    b = fixtures.building()
    return g, b


def _pts(doors):
    side = ["north", "east", "south", "west"]
    return {"adjacent": [{"lat_lng": [0, 0], "side": side[i % 4], "ground_ft": 50.0 + 0.1 * i} for i in range(8)],
            "around": [{"lat_lng": [0, 0], "side": "north", "ground_ft": 49.0}], "doors": doors, "footprint_perimeter_m": 100}


def _fl(level):
    return {"found": True, "elevation_ft": level, "elevation_ft_low": level - 0.2, "elevation_ft_high": level + 0.2,
            "stream": "S", "basis": "test", "cross_sections": [], "bfe_line_check": None, "nearest_distance_m": 50,
            "v_datum": ["NAVD88"], "len_unit": ["Feet"], "search_radius_m": 3000, "source": "test"}


def _door(i, kind, z):
    return {"entry_point_id": f"e{i}", "kind": kind, "lat_lng": [0, 0], "side": "south", "moved_m": 1, "ground_ft": z}


B = {"id": "t", "lat": 29.7, "lng": -95.3, "drive_in_bays": None, "loading_docks_external": None, "in_mapped_flood_zone": False}


def test_fixture_valid_and_matches_file():
    g, _ = _inputs()
    validate("grounding", g)
    assert fixtures.load("grounding.json") == g


def test_doors_ranked_by_ground_lowest_first():
    g = ground.assemble(B, _pts([_door(1, "door", 51.0), _door(2, "drive_in", 50.2), _door(3, "door", 50.9)]), _fl(48))
    assert [r["entry_point_id"] for r in g["entry_points"]] == ["e2", "e3", "e1"]
    assert g["first_door"]["entry_point_id"] == "e2" and g["first_door"]["lead_ft"] == 0.7
    assert g["entry_points"][2]["above_lowest_door_ft"] == 0.8


@pytest.mark.parametrize("doors,costar,aid", [
    ([_door(1, "drive_in", 50.0), _door(2, "dock", 47.0)], {}, "G-SLAB-GRADE"),        # drive-in governs
    ([_door(1, "dock", 47.0), _door(2, "door", 50.0)], {}, "G-SLAB-DOCK"),
    ([_door(1, "door", 50.0)], {}, "G-SLAB-STEP"),
    ([], {"drive_in_bays": 3}, "G-SLAB-GRADE"),                                         # CoStar door type, none mapped
    ([], {"loading_docks_external": 4}, "G-SLAB-DOCK"),
])
def test_slab_allowance_follows_door_type(doors, costar, aid):
    g = ground.assemble({**B, **costar}, _pts(doors), _fl(40))
    f = g["floor"]
    assert f["allowance_id"] == aid
    lo, hi = ground.SLAB[aid]["range_ft"]
    assert f["elevation_ft_low"] == pytest.approx(f["ground_ft"][0] + lo - ground.RMSE_FT, abs=0.051)
    assert f["elevation_ft_high"] == pytest.approx(f["ground_ft"][1] + hi + ground.RMSE_FT, abs=0.051)
    assert f["elevation_ft_low"] <= f["elevation_ft"] <= f["elevation_ft_high"]


def test_fema_level_above_or_below_the_floor():
    doors = [_door(1, "drive_in", 50.0)]
    below = ground.assemble(B, _pts(doors), _fl(47.0))
    r = next(x for x in below["reference_levels"] if x["id"] == "fema-1pct")
    assert r["depth_above_floor_ft"] == pytest.approx(47.0 - below["floor"]["elevation_ft"], abs=0.051)
    assert r["depth_above_floor_ft"] < 0
    assert "stays about" in r["sentence"] and "below this floor" in r["sentence"]
    assert "outside the 1% area" in r["sentence"]                                       # B is outside the zone
    assert r["depth_above_floor_ft_low"] <= r["depth_above_floor_ft"] <= r["depth_above_floor_ft_high"]
    above = ground.assemble({**B, "in_mapped_flood_zone": True}, _pts(doors), _fl(53.0))
    r = next(x for x in above["reference_levels"] if x["id"] == "fema-1pct")
    assert r["depth_above_floor_ft"] > 0 and "of water inside" in r["sentence"] and "at this building" in r["sentence"]


def test_datum_mismatch_keeps_fema_off_the_floor_scale():
    fl = _fl(50.0)
    fl["v_datum"] = ["NGVD29"]
    g = ground.assemble(B, _pts([_door(1, "door", 50.0)]), fl)
    assert g["datum"]["match"] is False
    assert not any(r["id"] == "fema-1pct" for r in g["reference_levels"])


def test_steps_are_floor_plus_depth_on_the_slider_grid():
    g, _ = _inputs()
    f = g["floor"]
    assert [s["depth_ft"] for s in g["steps"]] == [round(i * 0.25, 2) for i in range(33)]
    for s in g["steps"]:
        assert s["water_surface_ft"] == pytest.approx(f["elevation_ft"] + s["depth_ft"], abs=0.051)
        assert s["water_surface_ft_low"] <= s["water_surface_ft"] <= s["water_surface_ft_high"]


def test_no_flow_model_claimed():
    g, _ = _inputs()
    assert "does not simulate" in g["method"] and "not" in g["method"]
    assert any(a["id"] == "G-WSE" and "does not model rainfall" in a["text"] for a in g["assumptions"])
    assert next(a for a in g["assumptions"] if a["id"].startswith("G-SLAB"))["placeholder"] is True
