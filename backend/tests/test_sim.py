"""Contracts v1.3: median and 80% interval by simulation, measured counts and thresholds, standard-method comparison,
top contributors (judge feedback 2026-11-14)."""
import random

import pytest

from app import buildings
from app.loss import mitigations as engine
from app.loss import model, sim
from tests.test_loss import ASSETS, B, asset

STEPS = [i * 0.25 for i in range(33)]


def _random_assets(seed: int, n: int) -> list[dict]:
    rng = random.Random(seed)
    classes = [a for a in model.assumptions()["assets"] if a["high"] > 0]
    out = []
    for i in range(n):
        c = rng.choice(classes)
        lo = round(rng.uniform(0, 3), 2)
        out.append({"id": f"r{seed}-{i}", "room": "R", "room_id": "r", "category": c["category"], "label": c["id"],
                    "height_ft_low": lo, "height_ft_high": round(lo + rng.choice([0, 0.1, 0.5, 2]), 2),
                    "value_usd_low": c["low"], "value_usd_high": c["high"], "value_basis": c["id"]})
    return out


CASES = [ASSETS, _random_assets(1, 3), _random_assets(2, 25), _random_assets(3, 80), [asset(9, "it", 0.5, 0.5)]]


@pytest.mark.parametrize("assets", CASES)
def test_percentiles_ordered_monotone_and_inside_extreme_bounds(assets):
    d = sim.Draws(B, assets)
    prev = None
    for dep in STEPS:
        r = sim.summarise(d, dep)
        c_lo, c_hi = model.contents_loss(assets, dep)
        s_lo, s_hi, _ = model.structure_loss(B, dep)
        bounds = {"contents": (c_lo, c_hi), "structure": (s_lo, s_hi), "total": (c_lo + s_lo, c_hi + s_hi)}
        for k, (lo, hi) in bounds.items():
            p10, p50, p90 = r[k]
            assert p10 <= p50 <= p90, (dep, k)
            assert lo - 1e-6 <= p10 and p90 <= hi + 1e-6, (dep, k, lo, p10, p90, hi)
            if prev:
                for q in range(3):
                    assert r[k][q] >= prev[k][q] - 1e-9, (dep, k, q)    # no percentile falls as depth rises
        prev = r


@pytest.mark.parametrize("assets", CASES)
def test_clamp_only_removes_sampling_noise(assets):
    d = sim.Draws(B, assets)
    for dep in STEPS:
        raw = sim.summarise(d, dep, clamp=False)
        c_lo, c_hi = model.contents_loss(assets, dep)
        assert raw["contents"][0] >= c_lo * 0.97 - 1e-6 and raw["contents"][2] <= c_hi * 1.03 + 1e-6, dep


def test_zero_depth_gives_zero_everywhere():
    s = model.scenario(B, ASSETS, 0)
    assert all(s[k] == 0 for k in s if k.endswith("_usd_low") or k.endswith("_usd_median") or k.endswith("_usd_high"))
    assert s["top_contributors"] == [] and s["items_in_water"]["count_high"] == 0


def test_reproducible_and_keyed_by_asset():
    a = model.scenario(B, ASSETS, 2.0)
    sim._value_col.cache_clear(), sim._normal.cache_clear(), sim._uniform.cache_clear()
    assert model.scenario(B, ASSETS, 2.0) == a
    # Draws are keyed by asset id and class, not position: dropping one asset leaves the others' expected loss alone.
    full = sim.expected_by_asset(B, ASSETS, 2.0)
    fewer = sim.expected_by_asset(B, ASSETS[1:], 2.0)
    assert all(fewer[k] == full[k] for k in fewer)
    assert list(reversed(sim.expected_by_asset(B, list(reversed(ASSETS)), 2.0).items())) != [] and \
        sim.expected_by_asset(B, list(reversed(ASSETS)), 2.0) == full


def test_interval_narrower_than_the_old_sums():
    s = model.scenario(B, _random_assets(3, 80), 2.0)
    lo, hi = model.contents_loss(_random_assets(3, 80), 2.0)
    assert (s["loss_usd_high"] - s["loss_usd_low"]) < 0.6 * (hi - lo)


def test_value_draws_match_the_stated_distribution():
    one = [asset(1, "inventory", 0.0, 0.0, 1000, 9000)]
    v = sim.Draws(B, one).V[:, 0]
    p10, p50, p90 = sim.pct3(v)
    assert p10 == pytest.approx(1000, rel=0.05) and p90 == pytest.approx(9000, rel=0.05)
    assert p50 == pytest.approx(3000, rel=0.05)                       # geometric mean of 1,000 and 9,000


def test_class_correlation_is_the_stated_value():
    import numpy as np
    a, b = asset(1, "inventory", 0, 0, 1000, 9000), asset(2, "inventory", 0, 0, 1000, 9000)
    v = sim.Draws(B, [a, b]).V
    r = np.corrcoef(np.log(v[:, 0]), np.log(v[:, 1]))[0, 1]
    assert r == pytest.approx(sim.rho(), abs=0.05)
    c = asset(3, "it", 0, 0, 1000, 9000)
    v = sim.Draws(B, [a, c]).V
    assert abs(np.corrcoef(np.log(v[:, 0]), np.log(v[:, 1]))[0, 1]) < 0.06   # different classes: independent


def test_items_in_water_and_thresholds_are_measured():
    w = sim.in_water(ASSETS, 1.0)
    # contents items a1-a5 (no fabric or vehicles): bottom of range <= 1 ft: a1, a3, a5; top <= 1 ft: a1, a3, a5
    assert (w["of"], w["count_low"], w["count_high"]) == (5, 3, 3)
    w = sim.in_water(ASSETS, 2.0)
    assert (w["count_low"], w["count_high"]) == (3, 4)                # a4 HVAC 1.5-2.5 is only possibly reached
    t = sim.thresholds(ASSETS)
    assert t["first_loss_ft"] == [0.0, 0.5]
    assert t["half_items_ft"] == [0.3, 1.0]                             # 3rd of 5 lowest bottoms / tops
    assert t["most_items_ft"] == [1.5, 2.5]                             # 4th of 5
    elec = next(c for c in t["critical_systems"] if c["system"] == "electrical")
    assert elec["first_reached_ft"] == [3.5, 4.5] and elec["items"] == 1
    assert next(c for c in t["critical_systems"] if c["system"] == "it")["first_reached_ft"] == [0.3, 0.8]


def test_standard_method_is_hazus_on_the_same_values():
    fixed = [asset(1, "inventory", 0, 0, 1000, 1000), asset(2, "furniture", 0, 0, 2000, 2000)]
    s = model.scenario(B, fixed, 2.0)
    f = sim.standard_functions(B)                                       # COM2 defaults: inventory 33%, contents 27% at 2 ft
    assert f["inventory"]["function_id"] == 46 and f["contents"]["function_id"] == 195
    assert s["standard_contents_usd_median"] == round(1000 * 0.33 + 2000 * 0.27)
    t = model.scenario_table(B, ASSETS)
    sm = t["standard_method"]
    assert [c["depth_ft"] for c in sm["compare"]] == [1.0, 2.0, 4.0, 6.0]
    for c in sm["compare"]:
        assert c["verdict"] == sim.verdict(c["ours_median_usd"], c["standard_median_usd"])[0]
        assert f"at {c['depth_ft']:g} ft ours is {c['verdict']}" in sm["statement"]
    assert model.scenario({"id": "x"}, fixed, 2.0)["standard_contents_usd_median"] is None


def test_top_contributors():
    s = model.scenario(B, _random_assets(3, 80), 2.0)
    top = s["top_contributors"]
    assert 0 < len(top) <= 5
    assert [x["expected_loss_usd"] for x in top] == sorted((x["expected_loss_usd"] for x in top), reverse=True)
    assert 0 < sum(x["share"] for x in top) <= 1.0001


def test_table_rows_equal_scenario():
    t = model.scenario_table(B, ASSETS)
    for d in (0.0, 1.0, 2.75, 6.0):
        s = model.scenario(B, ASSETS, d)
        row = t["rows"][t["steps_ft"].index(d)]
        assert {k: v for k, v in row.items() if k != "depth_ft"} == \
            {k: v for k, v in s.items() if k in row and k != "depth_ft"}
    i = t["steps_ft"].index(2.0)
    exp = sim.expected_by_asset(B, ASSETS, 2.0)
    assert {a["asset_id"]: a["expected_loss_usd"][i] for a in t["assets"] if a["expected_loss_usd"][i]} == exp


@pytest.mark.parametrize("bid", ["building-e", "building-b"])
def test_real_buildings_properties(bid):
    if bid not in buildings.building_ids():
        pytest.skip("no cached building")
    b, a = buildings.get_building(bid), buildings.get_assets(bid)
    t = model.scenario_table(b, a)
    for prev, row in zip(t["rows"], t["rows"][1:]):
        for k in ("loss_usd", "structure_loss_usd", "total_usd"):
            assert row[f"{k}_low"] <= row[f"{k}_median"] <= row[f"{k}_high"]
            assert row[f"{k}_median"] >= prev[f"{k}_median"]
    eps = buildings.get_entry_points(bid)
    for m in engine.ranked(bid, engine.candidates(bid, a, eps), a, 2.0, engine.building_loss_fn(b)):
        assert m["avoided_loss_usd_low"] <= m["avoided_loss_usd_median"] <= m["avoided_loss_usd_high"]
