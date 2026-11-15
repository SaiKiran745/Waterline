"""Mitigation candidates, avoided loss and ranking (BUILD_PROMPTS Phase 4A step 3).

Candidates come from the assets and entry points. Ids are stable across depths: they depend on the action,
room and category, never on the depth. Avoided loss at a depth = loss without the action - loss with it.
Ranking is by avoided loss per dollar (median avoided loss / cost midpoint); actions that avoid nothing rank last.
Contracts v1.3: avoided loss is simulated with the same draws as the scenario (app/loss/sim.py), before and after
the action, so it has a median and an 80% interval like every other loss figure.
"""
from typing import Callable

import numpy as np

from app.loss import model, sim

RAISE_CATEGORIES = ("it", "hvac", "equipment")
LossFn = Callable[[list[dict], float], tuple[np.ndarray, np.ndarray]]   # contents and structure loss per simulated draw


def cost(mid: str) -> dict:
    return model.assumption_by_id(mid)


def candidates(bid: str, assets: list[dict], entry_points: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for a in assets:
        groups.setdefault((a.get("room_id") or a["room"], a["category"]), []).append(a)
    specs = []
    for (room_key, cat), items in sorted(groups.items()):
        room = items[0]["room"]
        n = len(items)
        if cat == "inventory":
            c = cost("M-MOVE-INV")
            specs.append({"kind": "move_inventory", "basis": c["id"], "target_ft": c["target_ft"],
                          "action": f"Move floor-level inventory in {room} onto racking above {c['target_ft']:g} ft before landfall",
                          "targets": [a["id"] for a in items], "cost": (c["low"], c["high"]), "group": (room_key, cat)})
        elif cat == "electrical":
            c = cost("M-ELEC-RAISE")
            specs.append({"kind": "relocate_asset", "basis": c["id"], "target_ft": c["target_ft"],
                          "action": f"Relocate {n} electrical item{'s' if n > 1 else ''} in {room} so live parts sit above {c['target_ft']:g} ft",
                          "targets": [a["id"] for a in items], "cost": (c["low"] * n, c["high"] * n), "group": (room_key, cat)})
        elif cat in RAISE_CATEGORIES:
            c = cost("M-PLATFORM")
            specs.append({"kind": "raise_asset", "basis": c["id"], "raise_by_ft": c["raise_by_ft"],
                          "action": f"Raise {n} {cat if cat != 'it' else 'IT'} item{'s' if n > 1 else ''} in {room} by {c['raise_by_ft']:g} ft on platforms or wall mounts",
                          "targets": [a["id"] for a in items], "cost": (c["low"] * n, c["high"] * n), "group": (room_key, cat)})
    vehicles = [a for a in assets if (model.assumption_by_id(a["value_basis"]) or {}).get("movable")]
    if vehicles:
        c = cost("M-MOVE-VEHICLES")
        n = len(vehicles)
        specs.append({"kind": "other", "basis": c["id"], "movable": True,
                      "action": f"Drive {n} road vehicle{'s' if n > 1 else ''} and trailers to high ground before landfall",
                      "targets": [a["id"] for a in vehicles], "cost": (c["low"] * n, c["high"] * n),
                      "group": ("all", "vehicles")})
    if entry_points:
        c = cost("M-BARRIER")
        n = len(entry_points)
        specs.append({"kind": "entry_barrier", "basis": c["id"], "rating_ft": c["rating_ft"],
                      "action": f"Deploy {c['rating_ft']:g} ft flood barriers at all {n} ground-level openings",
                      "targets": [e["id"] for e in entry_points], "cost": (c["low"] * n, c["high"] * n), "group": ("all", "entry")})
    for s in specs:
        s["id"] = f"{bid}-m-{s['kind'].replace('_', '-')}-{model.slug(s['group'][0])}-{model.slug(s['group'][1])}"
    return specs


def _moved(spec: dict, assets: list[dict]) -> list[dict]:
    targets = set(spec["targets"])
    out = []
    for a in assets:
        if a["id"] in targets:
            a = dict(a)
            if "raise_by_ft" in spec:
                a["height_ft_low"] += spec["raise_by_ft"]
                a["height_ft_high"] += spec["raise_by_ft"]
            elif "target_ft" in spec:
                a["height_ft_low"] = max(a["height_ft_low"], spec["target_ft"])
                a["height_ft_high"] = max(a["height_ft_high"], spec["target_ft"] + 0.5)
        out.append(a)
    return out


def evaluate(spec: dict, assets: list[dict], depth_ft: float, loss: LossFn) -> np.ndarray:
    """Avoided loss per simulated draw (the same draws before and after the action)."""
    c, st = loss(assets, depth_ft)
    if spec["kind"] == "entry_barrier":
        return c + st if depth_ft <= spec["rating_ft"] else np.zeros_like(c)
    moved, _ = loss(_moved(spec, assets), depth_ft)
    return np.maximum(c - moved, 0.0)


def ranked(bid: str, specs: list[dict], assets: list[dict], depth_ft: float, loss: LossFn) -> list[dict]:
    rows = []
    for s in specs:
        a_lo, a_med, a_hi = (sim.sig(x) for x in sim.pct3(evaluate(s, assets, depth_ft, loss)))
        c_lo, c_hi = s["cost"]
        ratio = a_med / ((c_lo + c_hi) / 2)
        if s.get("movable"):
            note = (f"Protects {len(s['targets'])} movable asset{'s' if len(s['targets']) > 1 else ''} at risk; "
                    "vehicle value is not in the contents loss, so the avoided loss is not priced")
        elif a_hi > 0:
            note = (f"At {depth_ft:g} ft it avoids about ${a_med:,} (80% interval ${a_lo:,}-{a_hi:,}) for "
                    f"${c_lo:,.0f}-{c_hi:,.0f}: about {ratio:.1f} times its cost in one event")
        else:
            note = f"Avoids no loss at {depth_ft:g} ft"
        rows.append(({"id": s["id"], "building_id": bid, "depth_ft": depth_ft, "rank": 0, "kind": s["kind"],
                      "action": s["action"], "targets": s["targets"], "cost_usd_low": c_lo, "cost_usd_high": c_hi,
                      "avoided_loss_usd_low": a_lo, "avoided_loss_usd_median": a_med, "avoided_loss_usd_high": a_hi,
                      "payback_note": note, "basis": s["basis"]}, ratio, a_hi))
    rows.sort(key=lambda r: (r[2] <= 0, -r[1], r[0]["id"]))
    for i, (m, _, _) in enumerate(rows, 1):
        m["rank"] = i
    return [m for m, _, _ in rows]


def building_loss_fn(building: dict, structure_fn=None) -> LossFn:
    def loss(assets, depth):
        d = sim.Draws(building, assets, structure_fn)
        m = d.contents(depth)
        return (m.sum(axis=1) if m.size else np.zeros(sim.draws())), d.structure(depth)
    return loss
