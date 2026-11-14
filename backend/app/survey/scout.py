"""Contents scout: a cheap first look at each candidate building, to pick the demo buildings.

    python -m app.survey.scout [building-a building-b ...]      (default: every shortlisted building except H)

For each building it reads 3 well-spread scan positions (one Gemini call each, the same call the full survey makes,
so the full survey reuses them from the cache) and counts contents assets: survey items that are not building fabric,
merged with the survey's own rule. A building is skipped if any face shows a children's space.
Writes data/cache/scout.json.
"""
import argparse
import json

import numpy as np

from app.buildings import building_ids, get_building
from app.config import BUILDINGS, CACHE, MEDIA
from app.sources import gemini, spend
from app.sources.cache import write_json
from app.survey.geometry import mesh_for
from app.survey.interior import merge, survey_position

OUT = CACHE / "scout.json"
N = 3


def spread_positions(mp: dict, n: int = N) -> list[dict]:
    """Most central position of the building, then farthest-point sampling over all positions with a panorama."""
    panos = {p["location_id"]: p for p in mp["panos"]}
    locs = [l for l in mp["locations"] if l["id"] in panos]
    pts = np.array([[l["position"]["x"], l["position"]["y"]] for l in locs])
    picks = [int(np.argmin(np.linalg.norm(pts - pts.mean(axis=0), axis=1)))]
    while len(picks) < min(n, len(locs)):
        d = np.min(np.linalg.norm(pts[:, None] - pts[picks][None], axis=2), axis=1)
        picks.append(int(np.argmax(d)))
    out = []
    for k, i in enumerate(picks):
        reason = (f"scout 1/{n}: most central of {len(locs)} positions" if k == 0 else
                  f"scout {k + 1}/{n}: farthest from the earlier scout positions")
        out.append({"location": locs[i], "pano": panos[locs[i]["id"]],
                    "room_id": (locs[i].get("room") or {}).get("id") or "none", "reason": reason})
    return out


def scout(bid: str) -> dict:
    mp = json.loads((BUILDINGS / bid / "parts.json").read_text())["matterport"]
    mesh = mesh_for(str(MEDIA / bid / "mesh" / "mesh_50k.obj"))
    log = {"calls": []}
    res = {"positions": [], "flags": {}}
    dets = []
    for pos in spread_positions(mp):
        got, flags = survey_position(bid, mesh, mp, pos, log)
        dets += got
        res["flags"].update({k: v for k, v in flags.items() if not v["clear"]})
        res["positions"].append({"location_id": pos["location"]["id"], "reason": pos["reason"], "items": len(got),
                                 "contents": sum(1 for d in got if not d.get("fabric")),
                                 "labels": [d["label"] for d in got if not d.get("fabric")]})
        print(f"  {bid} {pos['reason']}: {len(got)} items, {res['positions'][-1]['contents']} contents", flush=True)
    groups = [g for g in merge(dets) if not g[0].get("fabric")]
    res["contents_assets"] = len(groups)
    res["categories"] = {c: sum(1 for g in groups if g[0]["category"] == c) for c in sorted({g[0]["category"] for g in groups})}
    res["childrens_space"] = any("childrens_space" in v["reasons"] for v in res["flags"].values())
    res["calls"] = len(log["calls"])
    res["cached_calls"] = sum(1 for c in log["calls"] if c.get("cached"))
    return res


def main(bids: list[str]) -> None:
    out = json.loads(OUT.read_text()) if OUT.exists() else {}
    for bid in bids:
        b = get_building(bid)
        try:
            r = scout(bid)
        except (gemini.BillingError, spend.BudgetExceeded) as e:
            print(f"STOP: {e}")
            break
        except gemini.GeminiError as e:
            print(f"  {bid}: scout failed ({e})")
            continue
        r.update({"in_mapped_flood_zone": b["in_mapped_flood_zone"], "flood_zone": b.get("flood_zone"),
                  "property_subtype": b.get("property_subtype")})
        out[bid] = r
        write_json(OUT, out)
        print(f"{bid}: {r['contents_assets']} contents assets {r['categories']}; children's space: {r['childrens_space']}; "
              f"in 1% zone: {r['in_mapped_flood_zone']}; spend so far ${spend.summary()['total_usd']:.4f}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("buildings", nargs="*")
    a = ap.parse_args()
    main(a.buildings or sorted(b for b in building_ids() if b != "building-h"))
