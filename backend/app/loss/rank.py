"""Precompute loss at 1, 2 and 4 ft for every shortlisted building (triage map).

    python -m app.loss.rank
"""
import json

from app import buildings
from app.config import CACHE
from app.loss import model
from app.sources.cache import write_json

DEPTHS = (1, 2, 4)
RANK_FILE = CACHE / "rank.json"


def compute() -> dict:
    out = {}
    for b in buildings.list_buildings():
        assets = buildings.get_assets(b["id"])
        out[b["id"]] = {}
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


if __name__ == "__main__":
    r = compute()
    for bid, v in sorted(r.items(), key=lambda kv: -kv[1]["2"]["total"][1]):
        print(bid, {d: f"${x['total'][0]:,.0f}-{x['total'][1]:,.0f}" for d, x in v.items()}, f"assets={v['2']['assets']}")
