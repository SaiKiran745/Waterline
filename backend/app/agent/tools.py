"""The agent's tools: thin, traced wrappers over the real Waterline functions (no fake data).

- Each tool belongs to one subagent and emits its own AgentEvents (tool_call, observation, decision), saying when a
  result came from the cache.
- Long results go into dossier files in the agent's file system (/dossier/<id>/..., via a Command state update,
  mirrored to data/cache/agent/dossier/<id>/ and announced as artifact events). The tool message itself stays short,
  so the model's context stays small.
- The interior survey has a position budget (SETTINGS["max_positions"], 12 by default) out of every scan position.
  The surveyor sees all positions with coordinates, neighbours and a plain-language area, spreads out first, then
  goes deeper where it found contents. Each survey call adds to the positions read so far in this session.
"""
import json
from typing import Annotated

from deepagents.backends.utils import create_file_data
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

from app import buildings, corrections
from app.actions import playbook as playbook_html
from app.actions import report as report_html
from app.actions import send as send_action
from app.agent import events, memory
from app.config import BUILDINGS, CACHE
from app.loss import mitigations as engine
from app.loss import model
from app.sources import gemini, spend
from app.survey import interior, site

SETTINGS = {"cached_positions_only": False, "max_positions": 12}
STATE: dict[str, dict] = {}          # per building, per session: positions read so far
DOSSIER = CACHE / "agent" / "dossier"


def reset(bid: str) -> None:
    STATE[bid] = {"chosen": []}


def _call(role: str, name: str, args: dict, text: str | None = None) -> None:
    events.emit(role, "tool_call", text or f"{name}({', '.join(f'{k}={v}' for k, v in args.items())})",
                data={"tool": name, "args": args})


def _check(building_id: str) -> dict:
    if building_id not in buildings.building_ids():
        raise ValueError(f"unknown building {building_id}")
    return buildings.get_building(building_id)


def _reply(role: str, tool_call_id: str, summary: dict | str, files: dict[str, str]) -> Command:
    """Short tool message + dossier files written into the agent's state (and mirrored to disk)."""
    upd = {}
    for path, content in files.items():
        upd[path] = create_file_data(content)
        bid = path.split("/")[2]
        dest = DOSSIER / bid / path.split(f"/dossier/{bid}/", 1)[1]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        events.emit(role, "artifact", f"Wrote {path} ({len(content):,} characters)", refs=[path],
                    data={"path": path, "by": "tool"})
    text = summary if isinstance(summary, str) else json.dumps(summary, separators=(",", ":"))
    update = {"messages": [ToolMessage(text, tool_call_id=tool_call_id)]}
    if upd:
        update["files"] = upd
    return Command(update=update)


def _usd(r) -> str:
    return f"${r[0]:,.0f}-{r[1]:,.0f}"


# ------------------------------------------------------------------ site-scout

@tool(parse_docstring=True)
def get_site_context(building_id: str) -> str:
    """Flood and site context: FEMA zone, ground elevation (context only), CoStar door counts.

    Args:
        building_id: Building slug, for example building-e.
    """
    b = _check(building_id)
    _call("site-scout", "get_site_context", {"building_id": building_id})
    out = {"fema_zone": b.get("flood_zone"), "in_1pct_zone": b.get("in_mapped_flood_zone"),
           "ground_ft": b.get("ground_elevation_ft"), "costar_drive_in": b.get("drive_in_bays"),
           "costar_docks": b.get("loading_docks_external")}
    events.emit("site-scout", "observation",
                f"FEMA zone {out['fema_zone']} ({'inside' if out['in_1pct_zone'] else 'outside'} the 1% annual-chance "
                f"area); ground {out['ground_ft']} ft (context only); CoStar: {out['costar_drive_in']} drive-in bays, "
                f"{out['costar_docks']} docks.", data=out)
    return json.dumps(out)


@tool(parse_docstring=True)
def find_entry_points(building_id: str, tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """Find where water gets in from the Vexcel aerial images, ranked, and cross-checked against CoStar's door counts.

    Args:
        building_id: Building slug.
    """
    _check(building_id)
    _call("site-scout", "find_entry_points", {"building_id": building_id},
          "find_entry_points on the ortho and oblique aerial images")
    eps, log = site.scout(building_id, cache_only=(BUILDINGS / building_id / "site_log.json").exists())
    src = "from cache" if log["cached"] else f"live ({log['model']})"
    events.emit("site-scout", "observation",
                f"{len(eps)} entry points ({src}): " + "; ".join(f"{e['id']} {e['kind']}" for e in eps[:6]),
                refs=[e["id"] for e in eps], data={"cached": log["cached"]})
    for d in log.get("discrepancies") or []:
        events.emit("site-scout", "observation", f"Layer discrepancy: {d['text']}",
                    refs=[e["id"] for e in eps if e["kind"] == d["kind"]], data=d)
    doc = [f"# Entry points: {building_id}", "", "| Rank | Id | Kind | View | Confidence | Evidence |",
           "|---|---|---|---|---|---|"]
    doc += [f"| {i} | {e['id']} | {e['kind']} | {e['image_kind']} | {e['confidence']:.2f} | {e['evidence']} |"
            for i, e in enumerate(eps, 1)]
    doc += ["", "## Cross-check with CoStar"] + [f"- {k}: {v}" for k, v in log["count_check"].items()]
    doc += [f"- DISCREPANCY: {d['text']}" for d in log.get("discrepancies") or []]
    return _reply("site-scout", tool_call_id, {
        "entry_points": [f"{e['id']} {e['kind']} conf {e['confidence']:.2f}" for e in eps],
        "discrepancies": [d["text"] for d in log.get("discrepancies") or []],
        "details": f"/dossier/{building_id}/entry-points.md"}, {f"/dossier/{building_id}/entry-points.md": "\n".join(doc)})


# ------------------------------------------------------------------ interior-surveyor

def _mp(bid: str) -> dict:
    return json.loads((BUILDINGS / bid / "parts.json").read_text())["matterport"]


def _areas(bid: str, mp: dict) -> dict:
    """Plain-language area for every position: the room type seen there this session, otherwise the room's size and
    which part of the room the position is in."""
    with_pano = {p["location_id"] for p in mp["panos"]}
    locs = [l for l in mp["locations"] if l["id"] in with_pano]
    by_room: dict[str, list] = {}
    for l in locs:
        by_room.setdefault((l.get("room") or {}).get("id") or "none", []).append(l)
    rank = {rid: i for i, (rid, _) in enumerate(sorted(by_room.items(), key=lambda kv: -len(kv[1])), 1)}
    labels = {r["id"]: (r.get("label") or "").strip() for r in mp["rooms"]}
    room_of = {l["id"]: (l.get("room") or {}).get("id") or "none" for l in locs}
    seen: dict[str, str] = {}
    log_path = BUILDINGS / bid / "survey_log.json"
    chosen = {c["location_id"] for c in STATE.get(bid, {}).get("chosen", [])}
    if log_path.exists():
        for p in json.loads(log_path.read_text())["positions"]:
            if p["location_id"] in chosen and p.get("room_types") and p["location_id"] in room_of:
                seen.setdefault(room_of[p["location_id"]], p["room_types"][0])
    out = {}
    for rid, ls in by_room.items():
        xs = [l["position"]["x"] for l in ls]
        ys = [l["position"]["y"] for l in ls]
        long_x = (max(xs) - min(xs)) >= (max(ys) - min(ys))
        lo, hi = (min(xs), max(xs)) if long_x else (min(ys), max(ys))
        name = labels.get(rid) or seen.get(rid) or f"room {rank[rid]}"
        size = "largest room" if rank[rid] == 1 else f"{len(ls)} positions"
        state = "seen" if rid in seen else "not yet seen"
        for l in ls:
            v = l["position"]["x" if long_x else "y"]
            t = (v - lo) / (hi - lo) if hi > lo else 0.5
            part = "one end" if t < 0.25 else "the other end" if t > 0.75 else "the middle"
            out[l["id"]] = f"{name} ({size}, {state}), {part}" if len(ls) > 2 else f"{name} ({size}, {state})"
    return out


@tool(parse_docstring=True)
def list_scan_positions(building_id: str) -> str:
    """Every Matterport scan position with its area, floor-plan coordinates (m) and neighbouring positions.

    Args:
        building_id: Building slug.
    """
    _check(building_id)
    mp = _mp(building_id)
    with_pano = {p["location_id"] for p in mp["panos"]}
    locs = [l for l in mp["locations"] if l["id"] in with_pano]
    areas = _areas(building_id, mp)
    cached = interior.vision_index(building_id)
    _call("interior-surveyor", "list_scan_positions", {"building_id": building_id})
    rows = [{"id": l["id"][:6], "area": areas[l["id"]],
             "xy": [round(l["position"]["x"], 1), round(l["position"]["y"], 1)],
             "near": [n[:6] for n in (l.get("neighbors") or []) if n in with_pano][:6]} for l in locs]
    budget = SETTINGS["max_positions"]
    used = len(STATE.get(building_id, {}).get("chosen", []))
    events.emit("interior-surveyor", "observation",
                f"{len(locs)} scan positions in {len({a.split(' (')[0] for a in areas.values()})} areas; budget "
                f"{budget} positions ({budget - used} left); {len(cached & with_pano)} have cached vision answers.",
                data={"positions": len(locs), "budget": budget})
    return json.dumps({"budget_left": budget - used, "positions": rows}, separators=(",", ":"))


@tool(parse_docstring=True)
def survey_positions(building_id: str, choices: list[dict],
                     tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """Read the chosen scan positions with the vision model; adds to the positions already read this session.

    Args:
        building_id: Building slug.
        choices: Positions to read, each {"id": "<id from list_scan_positions>", "reason": "<plain words naming the area>"}.
    """
    _check(building_id)
    st = STATE.setdefault(building_id, {"chosen": []})
    mp = _mp(building_id)
    full = {p["location_id"] for p in mp["panos"]}
    have = {c["location_id"] for c in st["chosen"]}
    budget = SETTINGS["max_positions"] - len(st["chosen"])
    new, refused = [], []
    for c in choices or []:
        if not isinstance(c, dict):
            continue
        short = str(c.get("id") or c.get("location_id") or "")
        match = [f for f in full if f.startswith(short)] if short else []
        if len(match) != 1 or match[0] in have:
            refused.append(short)
            continue
        if len(new) >= budget:
            refused.append(f"{short} (over budget)")
            continue
        new.append({"location_id": match[0], "reason": str(c.get("reason") or "").strip()})
        have.add(match[0])
    _call("interior-surveyor", "survey_positions", {"building_id": building_id, "new_positions": len(new)},
          f"survey_positions: {len(new)} new positions ({len(st['chosen']) + len(new)} of "
          f"{SETTINGS['max_positions']} used)")
    for c in new:
        events.emit("interior-surveyor", "decision", f"Read position {c['location_id'][:6]}: {c['reason']}",
                    refs=[c["location_id"]])
    st["chosen"] += new
    backup = BUILDINGS / building_id / "assets_batch.json"
    if not backup.exists() and (BUILDINGS / building_id / "assets.json").exists():
        backup.write_text((BUILDINGS / building_id / "assets.json").read_text())
    try:
        assets = interior.run(building_id, SETTINGS["max_positions"], 0, SETTINGS["cached_positions_only"],
                              chosen=st["chosen"])
    except interior.Stop as e:
        events.emit("interior-surveyor", "observation", f"Survey stopped: {e}")
        return _reply("interior-surveyor", tool_call_id, {"stopped": str(e)[:200]}, {})
    log = json.loads((BUILDINGS / building_id / "survey_log.json").read_text())
    calls = {c["pano"]: c for c in log["calls"] if c["kind"] == "survey"}
    per = {p["location_id"]: p for p in log["positions"]}
    found = []
    for c in new:
        p = per.get(c["location_id"], {})
        call = calls.get(c["location_id"], {})
        f = {"id": c["location_id"][:6], "saw": (p.get("room_types") or ["?"])[0],
             "contents": len(p.get("contents") or []), "top": (p.get("contents") or [])[:3],
             "vehicles": p.get("vehicles", 0), "cached": bool(call.get("cached"))}
        found.append(f)
        events.emit("interior-surveyor", "observation",
                    f"Position {f['id']} ({'cached' if f['cached'] else 'live'}): saw a {f['saw']}; "
                    f"{f['contents']} contents items" + (f" ({', '.join(f['top'])})" if f["top"] else "")
                    + (f"; {f['vehicles']} vehicles" if f["vehicles"] else ""), refs=[c["location_id"]], data=f)
    low = sorted([a for a in assets if a["confidence"] < interior.LOW_CONF
                  and a["value_basis"] not in ("A-FIN", "V-VEHICLE")], key=lambda a: -a["value_usd_high"])
    contents = [a for a in assets if a["value_basis"] not in ("A-FIN", "V-VEHICLE")]
    value = [sum(a["value_usd_low"] for a in contents), sum(a["value_usd_high"] for a in contents)]
    events.emit("interior-surveyor", "observation",
                f"So far {len(st['chosen'])} positions, {len(contents)} contents assets worth {_usd(value)}; "
                f"{len(low)} below confidence {interior.LOW_CONF}.", refs=[a["id"] for a in low[:6]],
                data={"positions": len(st["chosen"]), "contents_assets": len(contents), "value_usd": value})
    doc = [f"# Interior inventory: {building_id}", "", f"Positions read: {len(st['chosen'])}", "",
           "| Id | Room | Asset | Class | Lowest part (ft) | Confidence |", "|---|---|---|---|---|---|"]
    doc += [f"| {a['id']} | {a['room']} | {a['label']} | {a['value_basis']} | {a['height_ft_low']}-{a['height_ft_high']} "
            f"| {a['confidence']} |" for a in assets]
    doc += ["", "## Positions", ""] + [f"- {c['location_id'][:6]}: {c['reason']}" for c in st["chosen"]]
    return _reply("interior-surveyor", tool_call_id, {
        "new_positions": found, "refused": refused, "budget_left": SETTINGS["max_positions"] - len(st["chosen"]),
        "contents_assets": len(contents), "contents_value_usd": value,
        "low_confidence": [f"{a['id']} {a['label'][:40]} conf {a['confidence']}" for a in low[:6]],
        "inventory": f"/dossier/{building_id}/inventory.md"}, {f"/dossier/{building_id}/inventory.md": "\n".join(doc)})


@tool(parse_docstring=True)
def relook_asset(building_id: str, asset_id: str) -> str:
    """Look again at a low-confidence asset from the nearest neighbouring scan position; updates it if the new view is more confident.

    Args:
        building_id: Building slug.
        asset_id: The asset to look at again.
    """
    _check(building_id)
    _call("interior-surveyor", "relook_asset", {"building_id": building_id, "asset_id": asset_id},
          f"relook_asset {asset_id} from a neighbouring scan position")
    try:
        r = interior.relook_asset(building_id, asset_id)
    except KeyError:
        return json.dumps({"error": f"unknown asset {asset_id}"})
    except (gemini.BillingError, spend.BudgetExceeded, gemini.GeminiError) as e:
        events.emit("interior-surveyor", "observation", f"Re-look of {asset_id} failed: {e}", refs=[asset_id])
        return json.dumps({"error": str(e)[:200]})
    b, a = r["before"], r["after"]
    if not r["neighbour_location_id"]:
        events.emit("interior-surveyor", "observation",
                    f"Could not re-look '{r['label']}': {r['result']}; the record stays at "
                    f"{b['height_ft_low']}-{b['height_ft_high']} ft, confidence {b['confidence']}.", refs=[asset_id], data=r)
        return json.dumps({"result": r["result"]})
    src = "from cache" if r["cached"] else f"live ({r['model']})"
    events.emit("interior-surveyor", "observation",
                f"Re-looked '{r['label']}' from neighbouring position {r['neighbour_location_id'][:6]} ({src}): "
                f"{b['height_ft_low']}-{b['height_ft_high']} ft at confidence {b['confidence']} -> "
                f"{a['height_ft_low']}-{a['height_ft_high']} ft at {a['confidence']}; {r['result']}.",
                refs=[asset_id, r["neighbour_location_id"]], data=r)
    return json.dumps({"result": r["result"], "before": b, "after": a})


# ------------------------------------------------------------------ market-analyst

@tool(parse_docstring=True)
def get_building_value(building_id: str) -> str:
    """CoStar building data behind the loss: type, size, year built, assessor improvement value, scan coverage.

    Args:
        building_id: Building slug.
    """
    b = _check(building_id)
    _call("market-analyst", "get_building_value", {"building_id": building_id})
    out = {"type": b.get("property_subtype"), "sqft": b.get("size_sqft"), "built": b.get("year_built"),
           "tenants": len(b.get("tenants") or []), "improvement_value_usd": b.get("improvement_value_usd"),
           "value_source": b.get("value_source"), "scan_coverage": b.get("scan_coverage"),
           "structure_basis_usd": model.structure_basis(b), "hazus_occupancy": model.occupancy_for(b)}
    events.emit("market-analyst", "observation",
                f"{out['type']}, {out['sqft']:,.0f} sq ft, built {out['built']}; assessor improvement value "
                f"${out['improvement_value_usd']:,.0f} x scan coverage {out['scan_coverage']:.0%} = structure basis "
                f"${out['structure_basis_usd']:,.0f}; Hazus occupancy {out['hazus_occupancy']}.", data=out)
    return json.dumps(out)


# ------------------------------------------------------------------ scenario-builder

@tool(parse_docstring=True)
def run_scenario(building_id: str, depth_ft: float, tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """Price the loss at a water depth above the ground-floor slab (0 to 8 ft): contents, structure, assets hit.

    Args:
        building_id: Building slug.
        depth_ft: Interior water depth in feet (a scenario the user chose, not a forecast).
    """
    b = _check(building_id)
    d = float(depth_ft)
    _call("scenario-builder", "run_scenario", {"building_id": building_id, "depth_ft": d})
    assets = buildings.get_assets(building_id)
    s = model.scenario(b, assets, d)
    spans = model._spans(assets)
    loss = {a["id"]: a["value_usd_high"] * model.fractions(a, d, spans.get(a["id"]))[1] for a in assets}
    top = sorted(assets, key=lambda a: -loss[a["id"]])[:3]
    vehicles = sum(1 for a in assets if a["value_basis"] == "V-VEHICLE" and d >= a["height_ft_low"])
    c, st = [s["loss_usd_low"], s["loss_usd_high"]], [s["structure_loss_usd_low"], s["structure_loss_usd_high"]]
    tot = [c[0] + st[0], c[1] + st[1]]
    likely = sum(1 for h in s["assets_hit"] if h["status"] == "likely")
    events.emit("scenario-builder", "observation",
                f"At {d:g} ft: contents {_usd(c)}, structure {_usd(st)}, total {_usd(tot)}; {likely} assets likely hit; "
                f"{vehicles} vehicles at risk.", refs=[a["id"] for a in top], data={"depth_ft": d, "total_usd": tot})
    doc = [f"# Scenario {d:g} ft: {building_id}", "", f"- Contents: {_usd(c)}", f"- Structure: {_usd(st)}",
           f"- Total: {_usd(tot)}", f"- Assets hit: {likely} likely, {len(s['assets_hit']) - likely} possible",
           f"- Vehicles at risk (not in contents loss): {vehicles}", "", "## Assumptions"]
    doc += [f"- {x['id']}{' (PLACEHOLDER)' if x['placeholder'] else ''}: {x['text']}" for x in s["assumptions"]]
    path = f"/dossier/{building_id}/scenario-{d:g}ft.md"
    return _reply("scenario-builder", tool_call_id, {
        "depth_ft": d, "contents": _usd(c), "structure": _usd(st), "total": _usd(tot), "likely_hit": likely,
        "top_assets": [a["label"][:40] for a in top], "vehicles_at_risk": vehicles,
        "placeholders": sorted({x["id"] for x in s["assumptions"] if x["placeholder"]}), "details": path},
        {path: "\n".join(doc)})


# ------------------------------------------------------------------ mitigation-planner

@tool(parse_docstring=True)
def rank_mitigations(building_id: str, depth_ft: float, tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """Rank the fixes at a depth by avoided loss per dollar: cost, avoided loss, payback note.

    Args:
        building_id: Building slug.
        depth_ft: Interior water depth in feet.
    """
    b = _check(building_id)
    d = float(depth_ft)
    _call("mitigation-planner", "rank_mitigations", {"building_id": building_id, "depth_ft": d})
    assets, eps = buildings.get_assets(building_id), buildings.get_entry_points(building_id)
    ms = engine.ranked(building_id, engine.candidates(building_id, assets, eps), assets, d, engine.building_loss_fn(b))
    events.emit("mitigation-planner", "observation",
                f"At {d:g} ft the top fixes are: " + "; ".join(f"{m['rank']}. {m['action']}" for m in ms[:3]),
                refs=[m["id"] for m in ms[:3]], data={"depth_ft": d, "order": [m["id"] for m in ms]})
    doc = [f"# Mitigations at {d:g} ft: {building_id}", "", "| Rank | Action | Cost | Avoided loss | Note |",
           "|---|---|---|---|---|"]
    doc += [f"| {m['rank']} | {m['action']} | {_usd([m['cost_usd_low'], m['cost_usd_high']])} | "
            f"{_usd([m['avoided_loss_usd_low'], m['avoided_loss_usd_high']])} | {m['payback_note']} |" for m in ms]
    path = f"/dossier/{building_id}/mitigations-{d:g}ft.md"
    return _reply("mitigation-planner", tool_call_id, {
        "depth_ft": d, "top": [f"{m['rank']}. {m['action']} (cost {_usd([m['cost_usd_low'], m['cost_usd_high']])}, "
                               f"avoids {_usd([m['avoided_loss_usd_low'], m['avoided_loss_usd_high']])})" for m in ms[:3]],
        "details": path}, {path: "\n".join(doc)})


# ------------------------------------------------------------------ communications

@tool(parse_docstring=True)
def draft_documents(building_id: str, depth_ft: float, tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """Render the resilience report and the room-by-room pre-storm playbook for a depth.

    Args:
        building_id: Building slug.
        depth_ft: Interior water depth in feet the documents are planned for.
    """
    b = _check(building_id)
    d = float(depth_ft)
    _call("communications", "draft_documents", {"building_id": building_id, "depth_ft": d})
    assets, eps = buildings.get_assets(building_id), buildings.get_entry_points(building_id)
    files = {f"/dossier/{building_id}/report.html": report_html.render(b, assets, eps, d),
             f"/dossier/{building_id}/playbook.html": playbook_html.render(b, assets, eps, d)}
    return _reply("communications", tool_call_id, {
        "report": f"/buildings/{building_id}/report?depth_ft={d:g}",
        "playbook": f"/buildings/{building_id}/playbook?depth_ft={d:g}"}, files)


@tool(parse_docstring=True)
def send_playbook(building_id: str, recipient: str, depth_ft: float) -> str:
    """Email the pre-storm playbook. A person must approve this call before it runs.

    Args:
        building_id: Building slug.
        recipient: Email address; must be in ALLOWED_RECIPIENTS.
        depth_ft: Depth the playbook was drafted for.
    """
    b = _check(building_id)
    d = float(depth_ft)
    html = playbook_html.render(b, buildings.get_assets(building_id), buildings.get_entry_points(building_id), d)
    out = send_action.send_playbook(building_id, recipient, d, html, approved=True)
    events.emit("communications", "observation", f"Approved send to {out['recipient']}: {out['status']} ({out['detail']})",
                data=out)
    return json.dumps({k: out[k] for k in ("status", "detail")})


# ------------------------------------------------------------------ orchestrator: memory of human corrections

@tool(parse_docstring=True)
def get_corrections(building_id: str) -> str:
    """Read the human corrections saved for this building (long-term memory) and the similar assets each could apply to.

    Args:
        building_id: Building slug.
    """
    _check(building_id)
    recs = corrections.load(building_id)
    _call("orchestrator", "get_corrections", {"building_id": building_id},
          f"Read {memory.agent_path(building_id)} ({len(recs)} corrections)")
    current = buildings.get_assets(building_id)
    by_id = {a["id"]: a for a in current}
    raw = {a["id"]: a for a in buildings.get_survey_assets(building_id)}
    sugg = []
    for rec in recs:
        if rec["by"] != "human" or rec["action"] != "patch":
            continue
        aid = corrections._match(rec, raw)
        if aid is None or aid not in by_id:
            continue
        done = {corrections._match(x, raw) for x in recs if x.get("propagated_from") == rec["id"]}
        sim = [a for a in corrections.similar(current, by_id[aid]) if a["id"] not in done and a["source"] == "vision"]
        if sim:
            sugg.append({"correction_id": rec["id"], "asset": f"{aid} {by_id[aid]['label']}", "changes": rec["changes"],
                         "note": rec.get("note"), "similar": [f"{a['id']} {a['label'][:40]}" for a in sim[:10]]})
    if recs:
        events.emit("orchestrator", "observation",
                    f"Memory: {len(recs)} correction(s) for {building_id}; {len(sugg)} could apply to similar assets.",
                    refs=[r["id"] for r in recs], data={"corrections": len(recs)})
    return json.dumps({"corrections": len(recs), "memory": memory.read_corrections(building_id)[-1500:] or "(none)",
                       "apply_to_similar": sugg})


@tool(parse_docstring=True)
def apply_correction_to_similar(building_id: str, correction_id: str, asset_ids: list[str], reason: str) -> str:
    """Apply a human correction to similar assets in the same building, recorded as propagated by the agent.

    Args:
        building_id: Building slug.
        correction_id: The human correction to copy.
        asset_ids: Similar assets to apply it to (ids as listed by get_corrections).
        reason: Why these assets are similar.
    """
    _check(building_id)
    src = next((r for r in corrections.load(building_id) if r["id"] == correction_id), None)
    if not src or src["action"] != "patch":
        return json.dumps({"error": f"no patch correction {correction_id}"})
    _call("orchestrator", "apply_correction_to_similar",
          {"building_id": building_id, "correction_id": correction_id, "assets": len(asset_ids)})
    done = []
    for aid in asset_ids:
        aid = str(aid).split()[0]
        try:
            corrections.record(building_id, buildings.get_assets(building_id), aid, "patch", dict(src["changes"]),
                               note=reason, by="agent", propagated_from=correction_id)
            done.append(aid)
        except (KeyError, corrections.CorrectionError):
            continue
    events.emit("orchestrator", "decision",
                f"Applied human correction {correction_id} ({', '.join(f'{k} -> {v}' for k, v in src['changes'].items())}) "
                f"to {len(done)} similar assets: {reason}", refs=done, data={"correction_id": correction_id})
    return json.dumps({"applied_to": done})


ROLE_TOOLS = {
    "site-scout": [get_site_context, find_entry_points],
    "interior-surveyor": [list_scan_positions, survey_positions, relook_asset],
    "market-analyst": [get_building_value],
    "scenario-builder": [run_scenario],
    "mitigation-planner": [rank_mitigations],
    "communications": [draft_documents],
}
ORCHESTRATOR_TOOLS = [get_corrections, apply_correction_to_similar, send_playbook]
