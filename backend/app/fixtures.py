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


# FIXTURE placeholder structure curve (C-STRUCT-FIXTURE): (depth ft, low USD, high USD). Before contracts v1.3 these
# were the structure figures in scenarios.json; since v1.3 that file holds the simulated percentiles over this curve.
STRUCTURE_CURVE = [(0, 0, 0), (1, 93000, 217000), (2, 186000, 372000), (4, 341000, 620000), (8, 558000, 992000)]


def _structure_points() -> list[tuple[float, float, float]]:
    return STRUCTURE_CURVE


def structure_fn(depth: float) -> tuple[float, float]:
    """The fixture's placeholder structure curve (FIXTURE, labelled placeholder); 0 with no water."""
    return (0.0, 0.0) if depth <= 0 else _interp(depth, _structure_points())


def scenario(depth_ft: float) -> dict:
    """The same method as real buildings (AGENTS.md section 9, simulated median and 80% interval, contracts v1.3) over
    the fixture assets, with the fixture's placeholder structure curve (FIXTURE, labelled placeholder)."""
    from app.loss import model
    rows = assets()
    known = {a["id"]: a for s in load("scenarios.json") for a in s["assumptions"]}
    out = model.scenario(building(), rows, depth_ft, structure_fn=structure_fn,
                         structure_entries=[known["C-STRUCT-FIXTURE"]])
    likely, possible = model.hits(rows, depth_ft)
    used = sorted({a["value_basis"] for a in likely + possible})
    out["assumptions"] = ([known[u] for u in used if u in known]
                          + ([model.as_entry(model.assumption_by_id("C-CONTENTS-DEPTH"))] if likely or possible else [])
                          + [known["C-STRUCT-FIXTURE"]]
                          + [a for a in out["assumptions"] if a["id"].startswith(("C-MC-", "X-EXTREME-BOUNDS"))])
    return out


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
    return engine.ranked(FIXTURE_ID, mitigation_specs(), assets(), depth_ft,
                         engine.building_loss_fn(building(), structure_fn=structure_fn))


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
    from app.loss import model, sim
    scen = load("scenarios.json")
    t = model.scenario_table(building(), assets(), structure_fn=structure_fn)
    known = {a["id"]: a for x in scen for a in x["assumptions"]}
    t["assumptions"] = [known[u] for u in sorted({a["value_basis"] for a in assets()}) if u in known] + \
        [model.as_entry(model.assumption_by_id("C-CONTENTS-DEPTH")), known["C-STRUCT-FIXTURE"]] + \
        sim.method_entries() + [a for a in t["assumptions"] if a["id"].startswith("X-EXTREME-BOUNDS")]
    return t


def triage() -> list[dict]:
    """FIXTURE triage: one row, the FIXTURE building (shape of GET /triage)."""
    rows = assets()
    def at(d):
        sc = scenario(d)
        return {"contents": [sc["loss_usd_low"], sc["loss_usd_high"]],
                "structure": [sc["structure_loss_usd_low"], sc["structure_loss_usd_high"]],
                "total": [sc["total_usd_low"], sc["total_usd_high"]], "contents_median": sc["loss_usd_median"],
                "structure_median": sc["structure_loss_usd_median"], "total_median": sc["total_usd_median"]}
    return [{"building_id": FIXTURE_ID, "rank": 1, "status": "surveyed", "positions_read": 12, "scan_positions": 40,
             "contents_assets": sum(1 for a in rows if a["category"] != "finishes"),
             "note": "FIXTURE, not real data.", "loss_by_depth_ft": {str(d): at(d) for d in (1, 2, 4, 6)}}]
