"""AGENTS.md section 9 loss model, Hazus curves, and one test per mitigation type."""
import pytest

from app.loss import mitigations as engine
from app.loss import model

B = {"id": "building-t", "property_type": "Industrial", "property_subtype": "Industrial_Warehouse",
     "improvement_value_usd": 1_000_000, "scan_coverage": 0.5}


def asset(i, cat, lo, hi, vlo=1000, vhi=2000, room="Warehouse"):
    return {"id": f"a{i}", "room": room, "room_id": room.lower(), "category": cat, "label": cat,
            "height_ft_low": lo, "height_ft_high": hi, "value_usd_low": vlo, "value_usd_high": vhi,
            "value_basis": model.asset_assumption(cat)["id"]}


ASSETS = [asset(1, "inventory", 0.0, 0.5, 5000, 50000), asset(2, "electrical", 3.5, 4.5, 3000, 25000, "Office"),
          asset(3, "it", 0.3, 0.8, room="Office"), asset(4, "hvac", 1.5, 2.5), asset(5, "equipment", 0.0, 1.0)]


def test_zero_depth_gives_zero_loss():
    s = model.scenario(B, ASSETS, 0)
    assert (s["loss_usd_low"], s["loss_usd_high"], s["structure_loss_usd_low"], s["structure_loss_usd_high"]) == (0, 0, 0, 0)
    assert s["assets_hit"] == []


def test_loss_never_decreases_and_low_not_above_high():
    prev = None
    for q in range(0, 33):
        s = model.scenario(B, ASSETS, q / 4)
        assert s["loss_usd_low"] <= s["loss_usd_high"] and s["structure_loss_usd_low"] <= s["structure_loss_usd_high"]
        if prev:
            for k in ("loss_usd_low", "loss_usd_high", "structure_loss_usd_low", "structure_loss_usd_high"):
                assert s[k] >= prev[k], (q / 4, k)
        prev = s


def test_likely_and_possible_rule():
    s = model.scenario(B, ASSETS, 2.0)
    status = {h["asset_id"]: h["status"] for h in s["assets_hit"]}
    assert status == {"a1": "likely", "a3": "likely", "a5": "likely", "a4": "possible"}
    # Fractional damage at 2 ft (C-CONTENTS-DEPTH): fraction = (depth - lowest point) / critical height, capped at 1.
    # a1 floor inventory (critical 1.5): low (2-0.5)/1.5 -> 1, high 1.  a3 IT (0.5): 1 and 1.
    # a4 HVAC (1.5): low lowest 2.5 -> 0, high (2-1.5)/1.5 = 1/3.  a5 other (2.0): low (2-1)/2 = 0.5, high 1.
    assert s["loss_usd_low"] == 5000 + 1000 + round(1000 * 0.5)
    assert s["loss_usd_high"] == round(50000 + 2000 + 2000 / 3 + 2000)


def test_structure_uses_hazus_curve_value_and_coverage():
    lo, hi = model.damage_pct("COM2", 2.0)
    s = model.scenario(B, [], 2.0)
    assert s["structure_loss_usd_low"] == round(1_000_000 * 0.5 * lo / 100)
    assert s["structure_loss_usd_high"] == round(1_000_000 * 0.5 * hi / 100)
    ids = {a["id"] for a in s["assumptions"]}
    assert "C-HAZUS-COM2" in ids and "S-VALUE-BASIS" in ids
    assert not any(a["placeholder"] for a in s["assumptions"] if a["id"] in ("C-HAZUS-COM2", "S-VALUE-BASIS"))


def test_occupancy_mapping():
    assert model.occupancy_for({"property_type": "GeneralRetail"}) == "COM1"
    assert model.occupancy_for({"property_type": "Flex", "property_subtype": "Flex_Showroom"}) == "IND2"
    assert model.occupancy_for(B) == "COM2"


def _all(depth, eps=()):
    specs = engine.candidates(B["id"], ASSETS, list(eps))
    return engine.ranked(B["id"], specs, ASSETS, depth, engine.building_loss_fn(B))


def _by_kind(depth, eps=()):
    return {m["kind"]: m for m in _all(depth, eps) if m["kind"] != "raise_asset"}, None


def test_move_inventory_avoids_floor_inventory_loss():
    m, _ = _by_kind(2.0)
    assert m["move_inventory"]["avoided_loss_usd_low"] == 5000 and m["move_inventory"]["avoided_loss_usd_high"] == 50000


def test_relocate_electrical_only_matters_when_water_reaches_it():
    assert _by_kind(2.0)[0]["relocate_asset"]["avoided_loss_usd_high"] == 0
    assert _by_kind(4.0)[0]["relocate_asset"]["avoided_loss_usd_high"] == 25000 * 0.5    # half a foot into a 1 ft critical height
    assert _by_kind(5.0)[0]["relocate_asset"]["avoided_loss_usd_high"] == 25000


def test_raise_asset_lifts_items_out_of_shallow_water():
    raised = [x for x in _all(1.0) if x["kind"] == "raise_asset"]
    assert raised and all(x["avoided_loss_usd_high"] >= 0 for x in raised)
    assert sum(x["avoided_loss_usd_high"] for x in raised) > 0


def test_entry_barrier_works_only_up_to_its_rating():
    eps = [{"id": "e1"}, {"id": "e2"}]
    at1 = _by_kind(1.0, eps)[0]["entry_barrier"]
    at3 = _by_kind(3.0, eps)[0]["entry_barrier"]
    s1 = model.scenario(B, ASSETS, 1.0)
    assert at1["avoided_loss_usd_high"] == s1["loss_usd_high"] + s1["structure_loss_usd_high"]
    rows = _all(3.0, eps)
    assert at3["avoided_loss_usd_high"] == 0
    assert all(at3["rank"] > x["rank"] for x in rows if x["avoided_loss_usd_high"] > 0)


def test_mitigation_ids_stable_across_depths():
    ids = [sorted(m["id"] for m in engine.ranked(B["id"], engine.candidates(B["id"], ASSETS, []), ASSETS, d,
                                                 engine.building_loss_fn(B))) for d in (0.5, 1, 2.75, 4, 8)]
    assert all(i == ids[0] for i in ids)


def test_contents_damage_rises_gradually_with_depth():
    racked = [asset(9, "inventory", 0.0, 0.2, 2000, 12000)]
    racked[0]["value_basis"] = "V-RACKED-INV"                  # critical 6 ft: water climbs the shelves
    seen = [model.contents_loss(racked, d)[1] for d in (1, 2, 4, 5, 6)]
    assert seen == sorted(seen) and len(set(seen)) == 5        # strictly rises up to 6 ft ...
    assert seen[-1] == model.contents_loss(racked, 8)[1] == 12000   # ... then the whole run is lost


def test_measured_object_height_caps_the_critical_height():
    a = asset(9, "inventory", 0.0, 0.0, 2000, 12000)
    a["value_basis"] = "V-RACKED-INV"
    assert model.critical_ft(a) == 6.0
    assert model.critical_ft(a, span_ft=2.0) == 2.0             # a 2 ft high rack is gone once water is 2 ft deep
    assert model.fractions(a, 2.0, 2.0) == (1.0, 1.0)


def test_scenario_table_matches_scenario_and_properties():
    t = model.scenario_table(B, ASSETS)
    assert t["steps_ft"][0] == 0 and t["steps_ft"][-1] == 8 and len(t["steps_ft"]) == 33
    first = t["rows"][0]
    assert first["loss_usd_low"] == first["loss_usd_high"] == first["structure_loss_usd_high"] == 0
    for prev, row in zip(t["rows"], t["rows"][1:]):
        for k in ("loss_usd_low", "loss_usd_high", "structure_loss_usd_low", "structure_loss_usd_high"):
            assert row[k] >= prev[k]
        assert row["loss_usd_low"] <= row["loss_usd_high"]
    for d in (1.0, 2.0, 4.25, 6.0):
        s = model.scenario(B, ASSETS, d)
        row = t["rows"][t["steps_ft"].index(d)]
        assert (row["loss_usd_low"], row["loss_usd_high"]) == (s["loss_usd_low"], s["loss_usd_high"])
        assert row["assets_hit"] == s["assets_hit"]
    for a in t["assets"]:
        assert all(lo <= hi for lo, hi in zip(a["fraction_low"], a["fraction_high"]))
        assert a["fraction_low"] == sorted(a["fraction_low"]) and a["fraction_high"] == sorted(a["fraction_high"])


def test_low_never_above_high_for_random_assets():
    import random
    rng = random.Random(7)
    ids = [a["id"] for a in model.assumptions()["assets"]]
    for _ in range(200):
        lo = round(rng.uniform(0, 5), 2)
        x = {"id": "r", "category": "other", "height_ft_low": lo, "height_ft_high": round(lo + rng.uniform(0, 3), 2),
             "value_basis": rng.choice(ids)}
        va = model.assumption_by_id(x["value_basis"])
        x["value_usd_low"], x["value_usd_high"] = va["low"], va["high"]
        span = rng.choice([None, round(rng.uniform(0.1, 8), 2)])
        prev = (0.0, 0.0)
        for d in [i * 0.25 for i in range(33)]:
            f_lo, f_hi = model.fractions(x, d, span)
            assert 0 <= f_lo <= f_hi <= 1 and f_lo >= prev[0] and f_hi >= prev[1]
            prev = (f_lo, f_hi)
