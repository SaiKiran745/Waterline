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


def assets() -> list[dict]:
    """Fixture assets with any corrections made through the API (stored under data/cache/, never in contracts/)."""
    from app import corrections
    return corrections.apply(FIXTURE_ID, load("assets.json"))


def detail() -> dict:
    return {"building": building(), "entry_points": load("entry_points.json"), "assets": assets()}


def _interp(depth: float, points: list[tuple[float, float, float]]) -> tuple[float, float]:
    for (d0, l0, h0), (d1, l1, h1) in zip(points, points[1:]):
        if d0 <= depth <= d1:
            t = (depth - d0) / (d1 - d0)
            return l0 + t * (l1 - l0), h0 + t * (h1 - h0)
    return points[-1][1], points[-1][2]


def scenario(depth_ft: float) -> dict:
    """AGENTS.md section 9 rule over the fixture assets. Depth 0 means no water, so nothing is hit.
    Structure loss interpolates the fixture's placeholder curve (FIXTURE, labelled placeholder)."""
    from app.loss import model
    rows = assets()
    likely, possible = model.hits(rows, depth_ft)
    c_lo, c_hi = model.contents_loss(rows, depth_ft)
    scen = load("scenarios.json")
    points = [(s["depth_ft"], s["structure_loss_usd_low"], s["structure_loss_usd_high"]) for s in scen]
    s_low, s_high = _interp(depth_ft, points)
    known = {a["id"]: a for s in scen for a in s["assumptions"]}
    used = sorted({a["value_basis"] for a in likely + possible})
    return {
        "building_id": FIXTURE_ID, "depth_ft": depth_ft,
        "depth_reference": "interior water depth above ground-floor slab",
        "loss_usd_low": round(c_lo), "loss_usd_high": round(c_hi),
        "assets_hit": [{"asset_id": a["id"], "status": "likely"} for a in likely]
                      + [{"asset_id": a["id"], "status": "possible"} for a in possible],
        "structure_loss_usd_low": round(s_low), "structure_loss_usd_high": round(s_high),
        "assumptions": [known[u] for u in used if u in known]
                       + ([model.as_entry(model.assumption_by_id("C-CONTENTS-DEPTH"))] if likely or possible else [])
                       + [known["C-STRUCT-FIXTURE"]],
    }


FIXTURE_PARAMS = {"move_inventory": {"target_ft": 3.0}, "raise_asset": {"raise_by_ft": 3.0},
                  "relocate_asset": {"target_ft": 4.0}, "entry_barrier": {"rating_ft": 2.0}}


def mitigation_specs() -> list[dict]:
    """The 5 fixture actions (stable ids m1-m5) as engine specs; avoided loss is recomputed at any depth."""
    seen, specs = set(), []
    for m in load("mitigations.json"):
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        specs.append({"id": m["id"], "kind": m["kind"], "action": m["action"], "targets": m["targets"],
                      "cost": (m["cost_usd_low"], m["cost_usd_high"]), "basis": m["basis"], **FIXTURE_PARAMS[m["kind"]]})
    return specs


def mitigations(depth_ft: float) -> list[dict]:
    from app.loss import mitigations as engine
    from app.loss.model import contents_loss

    def loss(assets, depth):
        c_lo, c_hi = contents_loss(assets, depth)
        s = scenario(depth)
        return c_lo, c_hi, s["structure_loss_usd_low"], s["structure_loss_usd_high"]
    return engine.ranked(FIXTURE_ID, mitigation_specs(), assets(), depth_ft, loss)


def report_html() -> str:
    b, s = building(), load("scenario_2ft.json")
    mit = "".join(f"<li>{html.escape(m['action'])}: cost ${m['cost_usd_low']:,}-{m['cost_usd_high']:,}, "
                  f"avoided ${m['avoided_loss_usd_low']:,}-{m['avoided_loss_usd_high']:,}</li>" for m in mitigations(2))
    assumptions = "".join(f"<li>{html.escape(a['id'])}: {html.escape(a['text'])}"
                          f"{' (assumed range, editable)' if a['placeholder'] else ''}</li>" for a in s["assumptions"])
    return (f"<article><h1>FIXTURE resilience report: {html.escape(b['name'])}</h1>"
            f"<p>FIXTURE, not real data. Scenario: 2 ft of water above the ground-floor slab.</p>"
            f"<p>Contents loss ${s['loss_usd_low']:,}-{s['loss_usd_high']:,}; structure loss "
            f"${s['structure_loss_usd_low']:,}-{s['structure_loss_usd_high']:,}.</p>"
            f"<h2>Ranked mitigations at 2 ft</h2><ol>{mit}</ol><h2>Assumptions</h2><ul>{assumptions}</ul></article>")


def playbook_html() -> str:
    rooms: dict[str, list[dict]] = {}
    for a in assets():
        rooms.setdefault(a["room"], []).append(a)
    body = "".join(
        f"<h2>{html.escape(room)}</h2><ul>"
        + "".join(f"<li>{html.escape(a['label'])}: lowest vulnerable part {a['height_ft_low']}-{a['height_ft_high']} ft</li>"
                  for a in sorted(items, key=lambda a: a["height_ft_low"]))
        + "</ul>" for room, items in rooms.items())
    return f"<article><h1>FIXTURE pre-storm playbook</h1><p>FIXTURE, not real data.</p>{body}</article>"


def scenario_table() -> dict:
    """The FIXTURE building's slider table: same contents method as real buildings, fixture structure curve."""
    from app.loss import model
    scen = load("scenarios.json")
    points = [(x["depth_ft"], x["structure_loss_usd_low"], x["structure_loss_usd_high"]) for x in scen]
    t = model.scenario_table(building(), assets(), structure_fn=lambda d: _interp(d, points))
    known = {a["id"]: a for x in scen for a in x["assumptions"]}
    t["assumptions"] = [known[u] for u in sorted({a["value_basis"] for a in assets()}) if u in known] + \
        [model.as_entry(model.assumption_by_id("C-CONTENTS-DEPTH")), known["C-STRUCT-FIXTURE"]]
    return t


def triage() -> list[dict]:
    """FIXTURE triage: one row, the FIXTURE building (shape of GET /triage)."""
    rows = assets()
    def at(d):
        sc = scenario(d)
        c = [sc["loss_usd_low"], sc["loss_usd_high"]]
        st = [sc["structure_loss_usd_low"], sc["structure_loss_usd_high"]]
        return {"contents": c, "structure": st, "total": [c[0] + st[0], c[1] + st[1]]}
    return [{"building_id": FIXTURE_ID, "rank": 1, "status": "surveyed", "positions_read": 12, "scan_positions": 40,
             "contents_assets": sum(1 for a in rows if a["category"] != "finishes"),
             "note": "FIXTURE, not real data.", "loss_by_depth_ft": {str(d): at(d) for d in (1, 2, 4, 6)}}]
