"""Loss model (AGENTS.md section 9).

- The slider is interior water depth above the ground-floor slab, 0 to 8 ft. Depth 0 means no water: zero loss.
- Asset hit: likely when depth >= height_ft_high, possible when height_ft_low <= depth < height_ft_high.
- Contents loss: low = sum value_usd_low over likely; high = sum value_usd_high over likely + possible.
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


def asset_assumption(category: str) -> dict:
    return next(a for a in assumptions()["assets"] if a["category"] == category)


def assumption_by_id(aid: str) -> dict | None:
    a = assumptions()
    return next((x for group in ("structure", "assets", "mitigations") for x in a[group] if x["id"] == aid), None)


def as_entry(a: dict) -> dict:
    """An assumption in ScenarioResult form."""
    text = a["text"]
    if "low" in a and "high" in a and a.get("category") != "finishes":
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
    likely, possible = hits(assets, depth_ft)
    return (float(sum(a["value_usd_low"] for a in likely)),
            float(sum(a["value_usd_high"] for a in likely + possible)))


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
    entries = [as_entry(assumption_by_id(u)) for u in used if assumption_by_id(u)] + s_entries
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
