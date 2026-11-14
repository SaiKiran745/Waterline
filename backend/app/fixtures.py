"""Fixture building `fixture-1` (contracts/fixtures/, FIXTURE, not real data), served until the real pipeline exists."""
import html
import json
from functools import lru_cache

from app.config import FIXTURES

FIXTURE_ID = "fixture-1"


@lru_cache(maxsize=None)
def load(name: str):
    return json.loads((FIXTURES / name).read_text())


def building() -> dict:
    return load("building.json")


def detail() -> dict:
    return {"building": building(), "entry_points": load("entry_points.json"), "assets": load("assets.json")}


def _interp(depth: float, points: list[tuple[float, float, float]]) -> tuple[float, float]:
    for (d0, l0, h0), (d1, l1, h1) in zip(points, points[1:]):
        if d0 <= depth <= d1:
            t = (depth - d0) / (d1 - d0)
            return l0 + t * (l1 - l0), h0 + t * (h1 - h0)
    return points[-1][1], points[-1][2]


def scenario(depth_ft: float) -> dict:
    """AGENTS.md section 9 rule over the fixture assets. Depth 0 means no water, so nothing is hit.
    Structure loss interpolates the fixture's placeholder curve (FIXTURE, labelled placeholder)."""
    assets = load("assets.json")
    if depth_ft <= 0:
        likely, possible = [], []
    else:
        likely = [a for a in assets if depth_ft >= a["height_ft_high"]]
        possible = [a for a in assets if a["height_ft_low"] <= depth_ft < a["height_ft_high"]]
    scen = load("scenarios.json")
    points = [(s["depth_ft"], s["structure_loss_usd_low"], s["structure_loss_usd_high"]) for s in scen]
    s_low, s_high = _interp(depth_ft, points)
    known = {a["id"]: a for s in scen for a in s["assumptions"]}
    used = sorted({a["value_basis"] for a in likely + possible})
    return {
        "building_id": FIXTURE_ID, "depth_ft": depth_ft,
        "depth_reference": "interior water depth above ground-floor slab",
        "loss_usd_low": sum(a["value_usd_low"] for a in likely),
        "loss_usd_high": sum(a["value_usd_high"] for a in likely + possible),
        "assets_hit": [{"asset_id": a["id"], "status": "likely"} for a in likely]
                      + [{"asset_id": a["id"], "status": "possible"} for a in possible],
        "structure_loss_usd_low": round(s_low), "structure_loss_usd_high": round(s_high),
        "assumptions": [known[u] for u in used if u in known] + [known["C-STRUCT-FIXTURE"]],
    }


def mitigations(depth_ft: float) -> list[dict]:
    """Fixture mitigations were evaluated at 1, 2 and 4 ft; return the set for the nearest depth at or below
    the request (each record carries its own depth_ft)."""
    rows = load("mitigations.json")
    depths = sorted({m["depth_ft"] for m in rows})
    pick = max([d for d in depths if d <= depth_ft], default=depths[0])
    return sorted([m for m in rows if m["depth_ft"] == pick], key=lambda m: m["rank"])


def report_html() -> str:
    b, s = building(), load("scenario_2ft.json")
    mit = "".join(f"<li>{html.escape(m['action'])}: cost ${m['cost_usd_low']:,}-{m['cost_usd_high']:,}, "
                  f"avoided ${m['avoided_loss_usd_low']:,}-{m['avoided_loss_usd_high']:,}</li>" for m in mitigations(2))
    assumptions = "".join(f"<li>{html.escape(a['id'])}: {html.escape(a['text'])}"
                          f"{' (PLACEHOLDER)' if a['placeholder'] else ''}</li>" for a in s["assumptions"])
    return (f"<article><h1>FIXTURE resilience report: {html.escape(b['name'])}</h1>"
            f"<p>FIXTURE, not real data. Scenario: 2 ft of water above the ground-floor slab.</p>"
            f"<p>Contents loss ${s['loss_usd_low']:,}-{s['loss_usd_high']:,}; structure loss "
            f"${s['structure_loss_usd_low']:,}-{s['structure_loss_usd_high']:,}.</p>"
            f"<h2>Ranked mitigations at 2 ft</h2><ol>{mit}</ol><h2>Assumptions</h2><ul>{assumptions}</ul></article>")


def playbook_html() -> str:
    assets = load("assets.json")
    rooms: dict[str, list[dict]] = {}
    for a in assets:
        rooms.setdefault(a["room"], []).append(a)
    body = "".join(
        f"<h2>{html.escape(room)}</h2><ul>"
        + "".join(f"<li>{html.escape(a['label'])}: lowest vulnerable part {a['height_ft_low']}-{a['height_ft_high']} ft</li>"
                  for a in sorted(items, key=lambda a: a["height_ft_low"]))
        + "</ul>" for room, items in rooms.items())
    return f"<article><h1>FIXTURE 72-hour pre-storm playbook</h1><p>FIXTURE, not real data.</p>{body}</article>"
