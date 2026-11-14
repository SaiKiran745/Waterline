"""Precompute loss at 1, 2 and 4 ft for every shortlisted building (triage map), labelled "surveyed" or
"structure only" so the ranking is honest about what it compares.

    python -m app.loss.rank
"""
import json

from app import buildings
from app.config import BUILDINGS, CACHE
from app.loss import model
from app.sources.cache import write_json

DEPTHS = (1, 2, 4)
RANK_FILE = CACHE / "rank.json"


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
    contents = sum(1 for a in assets if a["category"] != "finishes")
    return {"status": "surveyed", "positions_read": read, "scan_positions": total, "contents_assets": contents,
            "note": f"Interior survey read {read} of {total} scan positions; contents loss counts only what those "
                    "positions show."}


def compute() -> dict:
    out = {}
    for b in buildings.list_buildings():
        assets = buildings.get_assets(b["id"])
        out[b["id"]] = {"survey": survey_status(b["id"], assets)}
        for d in DEPTHS:
            s = model.scenario(b, assets, d)
            out[b["id"]][str(d)] = {"contents": [s["loss_usd_low"], s["loss_usd_high"]],
                                    "structure": [s["structure_loss_usd_low"], s["structure_loss_usd_high"]],
                                    "total": [s["loss_usd_low"] + s["structure_loss_usd_low"],
                                              s["loss_usd_high"] + s["structure_loss_usd_high"]],
                                    "assets": len(assets)}
    write_json(RANK_FILE, out)
    return out


def load() -> dict:
    return json.loads(RANK_FILE.read_text()) if RANK_FILE.exists() else {}


def triage(depth: str = "2") -> list[dict]:
    """Every building ranked by total loss (high end) at `depth` ft, each labelled surveyed or structure only."""
    r = load()
    rows = []
    for bid, v in r.items():
        rows.append({"building_id": bid, **v["survey"],
                     "loss_by_depth_ft": {d: {k: v[d][k] for k in ("contents", "structure", "total")} for d in map(str, DEPTHS)}})
    rows.sort(key=lambda x: (-x["loss_by_depth_ft"][depth]["total"][1], x["building_id"]))
    for i, x in enumerate(rows, 1):
        x["rank"] = i
    return rows


if __name__ == "__main__":
    r = compute()
    for x in triage():
        print(x["rank"], x["building_id"], f"{x['status']:<15}", f"{x['positions_read']:>2}/{x['scan_positions']:<3} positions",
              f"contents={x['contents_assets']:<3}",
              {d: f"${v['total'][0]:,.0f}-{v['total'][1]:,.0f}" for d, v in x["loss_by_depth_ft"].items()})
