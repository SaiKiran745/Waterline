"""Loss model (AGENTS.md section 9).

- The slider is interior water depth above the ground-floor slab, 0 to 8 ft. Depth 0 means no water: zero loss.
- Asset hit: likely when depth >= height_ft_high, possible when height_ft_low <= depth < height_ft_high.
- Contents loss (C-CONTENTS-DEPTH): each asset loses a fraction of its value that rises with water above its lowest
  vulnerable point, reaching 1 at the class's critical height (or the item's own height from the mesh, if lower).
  Low = value_usd_low x fraction with the lowest point at height_ft_high (likely hits only);
  high = value_usd_high x fraction with the lowest point at height_ft_low (likely + possible).
- Structure loss: Hazus 6.1 depth-damage % (curves.yaml) x assessor improvement value x scan coverage.
Interior loss covers the scanned area only (the assets come from the scan).
"""
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).parent
DEPTH_REFERENCE = "interior water depth above ground-floor slab"


@lru_cache(maxsize=1)
def assumptions() -> dict:
    return yaml.safe_load((HERE / "assumptions.yaml").read_text())


@lru_cache(maxsize=1)
def curves() -> dict:
    return yaml.safe_load((HERE / "curves.yaml").read_text())


DEFAULT_CLASS = {"electrical": "V-ELEC-GEAR", "it": "V-IT", "hvac": "V-HVAC", "inventory": "V-FLOOR-INV",
                 "equipment": "V-OTHER", "furniture": "V-OFFICE-FURN", "finishes": "A-FIN", "other": "V-OTHER"}
DEFAULT_CRITICAL_FT = {"electrical": 1.0, "it": 0.5, "hvac": 1.5, "inventory": 1.5, "equipment": 2.0,
                       "furniture": 2.5, "finishes": 1.0, "other": 2.0}   # for value ids outside assumptions.yaml (FIXTURE)
MIN_CRITICAL_FT = 0.25


def asset_assumption(category: str) -> dict:
    """Default value class for a contract category (used when a correction changes only the category)."""
    return assumption_by_id(DEFAULT_CLASS[category])


def critical_ft(asset: dict, span_ft: float | None = None) -> float:
    a = assumption_by_id(asset.get("value_basis") or "")
    c = (a or {}).get("critical_ft") or DEFAULT_CRITICAL_FT.get(asset["category"], 2.0)
    if span_ft:
        c = min(c, span_ft)
    return max(c, MIN_CRITICAL_FT)


def fraction(depth_ft: float, lowest_ft: float, critical: float) -> float:
    """Share of an item's value lost with water at depth_ft: 0 at or below its lowest vulnerable point, 1 at critical."""
    if depth_ft <= 0 or depth_ft <= lowest_ft:
        return 0.0
    return min(1.0, (depth_ft - lowest_ft) / critical)


def _spans(assets: list[dict]) -> dict:
    """Object heights from the mesh (asset_geometry.json written by the survey), keyed by asset id."""
    if not assets:
        return {}
    from app.config import BUILDINGS
    if not assets[0].get("building_id"):
        return {}
    path = BUILDINGS / assets[0]["building_id"] / "asset_geometry.json"
    return _read_geometry(str(path), path.stat().st_mtime) if path.exists() else {}


@lru_cache(maxsize=32)
def _read_geometry(path: str, mtime: float) -> dict:
    import json
    return {k: v.get("span_ft") for k, v in json.loads(Path(path).read_text()).items()}


def fractions(asset: dict, depth_ft: float, span_ft: float | None = None) -> tuple[float, float]:
    """(low, high) damage fraction of one asset at depth_ft."""
    c = critical_ft(asset, span_ft)
    return fraction(depth_ft, asset["height_ft_high"], c), fraction(depth_ft, asset["height_ft_low"], c)


def assumption_by_id(aid: str) -> dict | None:
    a = assumptions()
    return next((x for group in ("structure", "contents", "assets", "mitigations") for x in a.get(group, [])
                 if x["id"] == aid), None)


def as_entry(a: dict) -> dict:
    """An assumption in ScenarioResult form."""
    text = a["text"]
    if "low" in a and "high" in a and a.get("high"):
        text += f" (${a['low']:,}-{a['high']:,})"
    return {"id": a["id"], "text": text, "source": a["source"], "placeholder": bool(a["placeholder"])}


def occupancy_for(building: dict) -> str | None:
    m = curves()["mapping"]
    return m.get(building.get("property_subtype") or "") or m.get(building.get("property_type") or "")


def damage_pct(occupancy: str, depth_ft: float) -> tuple[float, float]:
    if depth_ft <= 0:
        return 0.0, 0.0
    c = curves()["curves"][occupancy]
    d = min(depth_ft, c["depth_ft"][-1])
    return float(np.interp(d, c["depth_ft"], c["low_pct"])), float(np.interp(d, c["depth_ft"], c["high_pct"]))


def hits(assets: list[dict], depth_ft: float) -> tuple[list[dict], list[dict]]:
    if depth_ft <= 0:
        return [], []
    likely = [a for a in assets if depth_ft >= a["height_ft_high"]]
    possible = [a for a in assets if a["height_ft_low"] <= depth_ft < a["height_ft_high"]]
    return likely, possible


def contents_loss(assets: list[dict], depth_ft: float) -> tuple[float, float]:
    spans = _spans(assets)
    lo = hi = 0.0
    for a in assets:
        f_lo, f_hi = fractions(a, depth_ft, spans.get(a["id"]))
        lo += a["value_usd_low"] * f_lo
        hi += a["value_usd_high"] * f_hi
    return lo, hi


def structure_basis(building: dict) -> float | None:
    v, cov = building.get("improvement_value_usd"), building.get("scan_coverage")
    return v * cov if v and cov else None


def structure_loss(building: dict, depth_ft: float) -> tuple[float, float, list[dict]]:
    occ, basis = occupancy_for(building), structure_basis(building)
    if not occ or basis is None:
        note = {"id": "S-NO-BASIS", "text": "Structure loss not computed: no Hazus occupancy mapping or no assessor value",
                "source": "Waterline method", "placeholder": False}
        return 0.0, 0.0, [note]
    lo, hi = damage_pct(occ, depth_ft)
    c = curves()["curves"][occ]
    curve_entry = {"id": c["id"],
                   "text": f"Hazus 6.1 structure depth-damage, {occ} {c['name']}: {lo:.1f}-{hi:.1f}% at {depth_ft:g} ft "
                           f"({c['range_basis']}; default function {c['default_function_id']}, {c['default_source']})",
                   "source": curves()["source"], "placeholder": False}
    basis_entry = as_entry(assumption_by_id("S-VALUE-BASIS"))
    basis_entry["text"] += (f" Basis ${building['improvement_value_usd']:,.0f} x scan coverage "
                            f"{building['scan_coverage']:.0%} = ${basis:,.0f}.")
    return basis * lo / 100.0, basis * hi / 100.0, [curve_entry, basis_entry]


def scenario(building: dict, assets: list[dict], depth_ft: float) -> dict:
    likely, possible = hits(assets, depth_ft)
    c_lo, c_hi = contents_loss(assets, depth_ft)
    s_lo, s_hi, s_entries = structure_loss(building, depth_ft)
    used = sorted({a["value_basis"] for a in likely + possible})
    entries = [as_entry(assumption_by_id(u)) for u in used if assumption_by_id(u)]
    if likely or possible:
        entries.append(as_entry(assumption_by_id("C-CONTENTS-DEPTH")))
    entries += s_entries
    return {
        "building_id": building["id"], "depth_ft": depth_ft, "depth_reference": DEPTH_REFERENCE,
        "loss_usd_low": round(c_lo), "loss_usd_high": round(c_hi),
        "assets_hit": [{"asset_id": a["id"], "status": "likely"} for a in likely]
                      + [{"asset_id": a["id"], "status": "possible"} for a in possible],
        "structure_loss_usd_low": round(s_lo), "structure_loss_usd_high": round(s_hi),
        "assumptions": entries,
    }


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "x"


STEP_FT = 0.25
MAX_FT = 8.0


def scenario_table(building: dict, assets: list[dict], structure_fn=None) -> dict:
    """Every slider step (0 to 8 ft by 0.25 ft) at once, with each asset's damage fraction per step (contracts v1.2)."""
    steps = [round(i * STEP_FT, 2) for i in range(int(MAX_FT / STEP_FT) + 1)]
    spans = _spans(assets)
    crit = {a["id"]: critical_ft(a, spans.get(a["id"])) for a in assets}
    structure_fn = structure_fn or (lambda d: structure_loss(building, d)[:2])
    rows, per_asset = [], {a["id"]: ([], []) for a in assets}
    for d in steps:
        c_lo = c_hi = 0.0
        likely, possible = [], []
        for a in assets:
            f_lo = fraction(d, a["height_ft_high"], crit[a["id"]])
            f_hi = fraction(d, a["height_ft_low"], crit[a["id"]])
            per_asset[a["id"]][0].append(round(f_lo, 3))
            per_asset[a["id"]][1].append(round(f_hi, 3))
            c_lo += a["value_usd_low"] * f_lo
            c_hi += a["value_usd_high"] * f_hi
            if d > 0 and d >= a["height_ft_high"]:
                likely.append({"asset_id": a["id"], "status": "likely"})
            elif d > 0 and d >= a["height_ft_low"]:
                possible.append({"asset_id": a["id"], "status": "possible"})
        s_lo, s_hi = structure_fn(d)
        rows.append({"depth_ft": d, "loss_usd_low": round(c_lo), "loss_usd_high": round(c_hi),
                     "structure_loss_usd_low": round(s_lo), "structure_loss_usd_high": round(s_hi),
                     "total_usd_low": round(c_lo) + round(s_lo), "total_usd_high": round(c_hi) + round(s_hi),
                     "assets_hit": likely + possible})
    used = sorted({a["value_basis"] for a in assets})
    entries = [as_entry(assumption_by_id(u)) for u in used if assumption_by_id(u)]
    entries.append(as_entry(assumption_by_id("C-CONTENTS-DEPTH")))
    if building.get("id") and occupancy_for(building) is not None:
        entries += structure_loss(building, MAX_FT)[2][1:]          # value basis (curve text is per depth)
        c = curves()["curves"][occupancy_for(building)]
        entries.insert(len(entries) - 1, {"id": c["id"], "text": f"Hazus 6.1 structure depth-damage, {occupancy_for(building)} "
                                          f"{c['name']} ({c['range_basis']})", "source": curves()["source"],
                                          "placeholder": False})
    return {"building_id": building["id"], "depth_reference": DEPTH_REFERENCE, "step_ft": STEP_FT,
            "steps_ft": steps, "rows": rows,
            "assets": [{"asset_id": a["id"], "value_basis": a["value_basis"], "value_usd_low": a["value_usd_low"],
                        "value_usd_high": a["value_usd_high"], "critical_ft": round(crit[a["id"]], 2),
                        "movable": bool((assumption_by_id(a["value_basis"]) or {}).get("movable")),
                        "fraction_low": per_asset[a["id"]][0], "fraction_high": per_asset[a["id"]][1]}
                       for a in assets],
            "assumptions": entries}
