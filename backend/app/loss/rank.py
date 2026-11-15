"""Precompute loss at 1, 2 and 4 ft for every shortlisted building (triage map), labelled "surveyed" or
"structure only" so the ranking is honest about what it compares.

    python -m app.loss.rank
"""
import json

from app import buildings
from app.config import BUILDINGS, CACHE
from app.loss import model
from app.sources.cache import write_json

DEPTHS = (1, 2, 4, 6)
OFFSETS = (0, 1, 2, 3)            # elevation mode: FEMA's 1% level + this many ft (contracts v1.3)
RANK_FILE = CACHE / "rank.json"
FAR_M = 500                       # beyond this the nearest FEMA level is called a weak reference


def survey_status(bid: str, assets: list[dict]) -> dict:
    """'surveyed' only when an interior survey ran; otherwise the loss is structure only and not comparable."""
    log_path = BUILDINGS / bid / "survey_log.json"
    mp = json.loads((BUILDINGS / bid / "parts.json").read_text()).get("matterport") or {}
    total = len(mp.get("panos") or [])
    if not log_path.exists():
        return {"status": "structure only", "positions_read": 0, "scan_positions": total, "contents_assets": 0,
                "note": "No interior survey yet: loss is the structure curve only, so it is not comparable with "
                        "surveyed buildings."}
    log = json.loads(log_path.read_text())
    read = sum(1 for x in log["positions"] if not x.get("error"))
    contents = sum(1 for a in assets if a["value_basis"] not in ("A-FIN", "V-VEHICLE"))   # as the agent counts them
    vehicles = sum(1 for a in assets if a["value_basis"] == "V-VEHICLE")
    return {"status": "surveyed", "positions_read": read, "scan_positions": total, "contents_assets": contents,
            "note": f"Interior survey read {read} of {total} scan positions; {contents} contents assets"
                    + (f" (plus {vehicles} road vehicles, listed as movable and not in contents loss)" if vehicles else "")
                    + ("" if read == total else "; contents loss counts only what those positions show") + "."}


def _loss(s: dict) -> dict:
    return {"contents": [s["loss_usd_low"], s["loss_usd_high"]], "contents_median": s["loss_usd_median"],
            "structure": [s["structure_loss_usd_low"], s["structure_loss_usd_high"]],
            "structure_median": s["structure_loss_usd_median"],
            "total": [s["total_usd_low"], s["total_usd_high"]], "total_median": s["total_usd_median"]}


def elevation_entry(building: dict, g: dict | None, offset: float, scenario_fn) -> dict:
    """One building in the elevation mode: a common outside water level (FEMA's 1% level + offset), the interior
    depth it gives over this building's floor (never below zero, capped at the slider's 8 ft) with its range from
    the elevation uncertainty, and the loss at that depth. scenario_fn(depth) -> ScenarioResult."""
    fl = (g or {}).get("fema_1pct") or {}
    if not g or not fl.get("found") or not g["datum"]["match"]:
        why = ("no elevation grounding yet" if not g else "no FEMA 1% level found nearby" if not fl.get("found")
               else "FEMA and USGS datums differ")
        return {"elevation": "missing", "missing_reason": why, "offset_ft": offset, "water_level_ft": None,
                "water_level_ft_low": None, "water_level_ft_high": None, "fema_level_ft": None, "fema_distance_m": None,
                "fema_at_building": None, "floor_ft": None, "floor_ft_low": None, "floor_ft_high": None,
                "floor_above_fema_ft": None, "water_above_floor_ft": None, "interior_depth_ft": None, "interior_depth_ft_low": None,
                "interior_depth_ft_high": None, "depth_capped": False, "loss": None, "total_median_at_depth_range": None,
                "sentence": f"Not ranked by elevation: {why}.", "depth_sentence": ""}
    f = g["floor"]
    clamp = lambda x: round(min(max(x, 0.0), model.MAX_FT), 2)
    wl, wl_lo, wl_hi = fl["elevation_ft"] + offset, fl["elevation_ft_low"] + offset, fl["elevation_ft_high"] + offset
    raw = wl - f["elevation_ft"]
    d, d_lo, d_hi = clamp(raw), clamp(wl_lo - f["elevation_ft_high"]), clamp(wl_hi - f["elevation_ft_low"])
    capped = (wl_hi - f["elevation_ft_low"]) > model.MAX_FT
    at_building = bool(building.get("in_mapped_flood_zone"))
    above = round(f["elevation_ft"] - fl["elevation_ft"], 1)
    where = "" if at_building else (f" (the nearest mapped level, {fl['nearest_distance_m']:,} m away"
                                     + ("; a weak reference" if fl["nearest_distance_m"] > FAR_M else "") + ")")
    sentence = (f"Floor is {abs(above):.1f} ft {'above' if above >= 0 else 'below'} FEMA's 1% level{where}."
                if abs(above) >= 0.05 else f"Floor is level with FEMA's 1% level{where}.")
    level = f"FEMA's 1% level{f' + {offset:g} ft' if offset else ''} ({wl:.1f} ft NAVD 88)"
    rng = (f"range {d_lo:.1f}-{d_hi:.1f} ft{', capped at the 8 ft slider' if capped else ''}" if d_hi > 0
           else "below the floor across the whole elevation range")
    depth_sentence = (f"At {level} the water stands about {d:.1f} ft above the floor ({rng})." if raw > 0 else
                      f"At {level} the water stays about {-raw:.1f} ft below the floor: no water inside ({rng}).")
    s = scenario_fn(d)
    return {"elevation": "ok", "missing_reason": None, "offset_ft": offset, "water_level_ft": round(wl, 2),
            "water_level_ft_low": round(wl_lo, 2), "water_level_ft_high": round(wl_hi, 2),
            "fema_level_ft": fl["elevation_ft"], "fema_distance_m": fl["nearest_distance_m"], "fema_at_building": at_building,
            "floor_ft": f["elevation_ft"], "floor_ft_low": f["elevation_ft_low"], "floor_ft_high": f["elevation_ft_high"],
            "floor_above_fema_ft": above, "water_above_floor_ft": round(raw, 2), "interior_depth_ft": d, "interior_depth_ft_low": d_lo, "interior_depth_ft_high": d_hi,
            "depth_capped": capped, "loss": _loss(s),
            "total_median_at_depth_range": [scenario_fn(d_lo)["total_usd_median"], scenario_fn(d_hi)["total_usd_median"]],
            "sentence": sentence, "depth_sentence": depth_sentence}


def compute() -> dict:
    from app.loss import grounding
    out = {}
    for b in buildings.list_buildings():
        assets = buildings.get_assets(b["id"])
        out[b["id"]] = {"survey": survey_status(b["id"], assets)}
        g = grounding.load(b["id"])
        out[b["id"]]["fema"] = {str(o): elevation_entry(b, g, o, lambda d: model.scenario(b, assets, d)) for o in OFFSETS}
        for d in DEPTHS:
            s = model.scenario(b, assets, d)
            out[b["id"]][str(d)] = {"contents": [s["loss_usd_low"], s["loss_usd_high"]],
                                    "structure": [s["structure_loss_usd_low"], s["structure_loss_usd_high"]],
                                    "total": [s["total_usd_low"], s["total_usd_high"]],
                                    "contents_median": s["loss_usd_median"],
                                    "structure_median": s["structure_loss_usd_median"],
                                    "total_median": s["total_usd_median"],
                                    "assets": len(assets)}
    write_json(RANK_FILE, out)
    return out


def load() -> dict:
    return json.loads(RANK_FILE.read_text()) if RANK_FILE.exists() else {}


KEYS = ("contents", "structure", "total", "contents_median", "structure_median", "total_median")


def triage(depth: str = "2") -> list[dict]:
    """Every building ranked by its median total loss at `depth` ft (contracts v1.3), each labelled surveyed or
    structure only. [low, high] is the 80% interval (10th-90th percentile)."""
    r = load()
    rows = []
    for bid, v in r.items():
        rows.append({"building_id": bid, **v["survey"],
                     "loss_by_depth_ft": {d: {k: v[d][k] for k in KEYS} for d in map(str, DEPTHS)}})
    rows.sort(key=lambda x: (-x["loss_by_depth_ft"][depth]["total_median"], x["building_id"]))
    for i, x in enumerate(rows, 1):
        x["rank"] = i
    return rows


def triage_elevation(offset: str = "0") -> list[dict]:
    """Elevation mode (contracts v1.3): every building at the same outside water level (FEMA's 1% level + offset),
    ranked by median total loss at the interior depth that level gives. Ties (for example several with no water
    inside) go to the building whose floor the water comes closest to. Buildings without elevation rank last."""
    r = load()
    rows = []
    for bid, v in r.items():
        if "fema" not in v:
            continue
        rows.append({"building_id": bid, **v["survey"], **v["fema"][offset]})
    rows.sort(key=lambda x: (x["elevation"] != "ok", -((x["loss"] or {}).get("total_median") or 0),
                             -(x["water_above_floor_ft"] if x["water_above_floor_ft"] is not None else -1e9), x["building_id"]))
    for i, x in enumerate(rows, 1):
        x["rank"] = i
    return rows


if __name__ == "__main__":
    r = compute()
    for x in triage():
        print(x["rank"], x["building_id"], f"{x['status']:<15}", f"{x['positions_read']:>2}/{x['scan_positions']:<3} positions",
              f"contents={x['contents_assets']:<3}",
              {d: f"${v['total_median']:,.0f} ({v['total'][0]:,.0f}-{v['total'][1]:,.0f})" for d, v in x["loss_by_depth_ft"].items()})
