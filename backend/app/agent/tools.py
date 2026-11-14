"""The agent's tools: thin, traced wrappers over the real Waterline functions (no fake data).

- Each tool belongs to one subagent and emits its own AgentEvents (tool_call, observation, decision), saying when a
  result came from the cache.
- Long results go into dossier files in the agent's file system (/dossier/<id>/..., via a Command state update,
  mirrored to data/cache/agent/dossier/<id>/ and announced as artifact events). The tool message itself stays short,
  so the model's context stays small.
- The interior survey reads every scan position by default, in batches of whole areas, largest first, with a
  plain-language reason per batch. SETTINGS["quick_scan"] (optional, off by default) sets a position budget split
  across areas by size. Every batch adds to the stored survey, which never shrinks (interior.run keep_stored).
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
from app.agent import events, guard, memory
from app.config import BUILDINGS, CACHE
from app.loss import mitigations as engine
from app.loss import model
from app.sources import gemini, spend
from app.survey import interior, site

SETTINGS = {"cached_positions_only": False, "quick_scan": None}   # quick_scan: optional position budget, off by default
STATE: dict[str, dict] = {}          # per building, per session: positions read so far and batches
DOSSIER = CACHE / "agent" / "dossier"


def reset(bid: str) -> None:
    STATE[bid] = {"chosen": [], "batches": 0}


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
    tr = events.current()
    if tr is not None:                      # figures the orchestrator may quote (agent/guard.py)
        tr.sources += list(files.values()) + [summary if isinstance(summary, str) else json.dumps(summary)]
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
    """Site context (FEMA zone, CoStar door counts) and where water gets in from the Vexcel aerial images, ranked and cross-checked.

    Args:
        building_id: Building slug.
    """
    b = _check(building_id)
    events.emit("site-scout", "observation",
                f"FEMA zone {b.get('flood_zone')} ({'inside' if b.get('in_mapped_flood_zone') else 'outside'} the 1% "
                f"annual-chance area); ground {b.get('ground_elevation_ft')} ft (context only); CoStar: "
                f"{b.get('drive_in_bays')} drive-in bays, {b.get('loading_docks_external')} docks.")
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
        "fema_zone": b.get("flood_zone"), "in_1pct_zone": b.get("in_mapped_flood_zone"),
        "lowest_door": f"{eps[0]['id']} {eps[0]['kind']}" if eps else None,
        "entry_points": [f"{e['id']} {e['kind']} conf {e['confidence']:.2f}" for e in eps],
        "discrepancies": [d["text"] for d in log.get("discrepancies") or []],
        "details": f"/dossier/{building_id}/entry-points.md"}, {f"/dossier/{building_id}/entry-points.md": "\n".join(doc)})


# ------------------------------------------------------------------ interior-surveyor

def _mp(bid: str) -> dict:
    return json.loads((BUILDINGS / bid / "parts.json").read_text())["matterport"]


ORDER = {1: "the largest room", 2: "the second-largest room", 3: "the third-largest room"}


def quota(sizes: list[int], budget: int | None) -> list[int]:
    """Positions to read per area. Full survey (budget None): all of them. Quick scan: the budget split across areas
    in proportion to their size (largest remainder), never more than an area has."""
    if budget is None or budget >= sum(sizes):
        return list(sizes)
    share = [budget * s / sum(sizes) for s in sizes]
    q = [min(s, int(x)) for s, x in zip(sizes, share)]
    for i in sorted(range(len(sizes)), key=lambda i: (-(share[i] - int(share[i])), -sizes[i])):
        if sum(q) >= budget:
            break
        if q[i] < sizes[i]:
            q[i] += 1
    return q


def _area_table(bid: str, mp: dict) -> list[dict]:
    """Rooms of the scan as areas A1, A2, ... largest first, named by what was seen in them this session (otherwise
    by size), with how many positions this run reads in each."""
    with_pano = {p["location_id"] for p in mp["panos"]}
    by_room: dict[str, list] = {}
    for l in mp["locations"]:
        if l["id"] in with_pano:
            by_room.setdefault((l.get("room") or {}).get("id") or "none", []).append(l)
    rooms = sorted(by_room.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    labels = {r["id"]: (r.get("label") or "").strip() for r in mp["rooms"]}
    st = STATE.get(bid, {"chosen": []})
    mine = {c["location_id"] for c in st["chosen"]}
    seen: dict[str, list[str]] = {}
    log_path = BUILDINGS / bid / "survey_log.json"
    if log_path.exists():
        for p in json.loads(log_path.read_text())["positions"]:
            if p["location_id"] in mine and p.get("room_types"):
                seen.setdefault(p["location_id"], p["room_types"])
    corrected = {(r.get("fingerprint") or {}).get("location_id") for r in corrections.load(bid) if r["by"] == "human"}
    q = quota([len(ls) for _, ls in rooms], SETTINGS["quick_scan"])
    out = []
    for i, ((rid, ls), n) in enumerate(zip(rooms, q), 1):
        types = [t for l in ls for t in seen.get(l["id"], [])]
        name = labels.get(rid) or (max(set(types), key=types.count) if types else ORDER.get(i, f"small room {i}"))
        out.append({"id": f"A{i}", "room_id": rid, "name": name, "size_rank": ORDER.get(i, f"small room {i}"),
                    "locs": ls, "to_read": n, "read": [l["id"] for l in ls if l["id"] in mine],
                    "corrected": [l["id"] for l in ls if l["id"] in corrected]})
    return out


def _stored(bid: str, mp: dict) -> str:
    return f"{len(interior.stored_read(bid))} of {len(mp['panos'])} positions read"


def _spread(locs: list[dict], n: int, must: list[str]) -> list[dict]:
    """n positions spread over an area: corrected positions first, then farthest-point from those chosen."""
    picks = [l for l in locs if l["id"] in must][:n]
    rest = [l for l in locs if l not in picks]
    if not picks and rest and n:
        cx = sum(l["position"]["x"] for l in rest) / len(rest)
        cy = sum(l["position"]["y"] for l in rest) / len(rest)
        first = min(rest, key=lambda l: (l["position"]["x"] - cx) ** 2 + (l["position"]["y"] - cy) ** 2)
        picks.append(first)
        rest.remove(first)
    while len(picks) < n and rest:
        far = max(rest, key=lambda l: min((l["position"]["x"] - p["position"]["x"]) ** 2 +
                                          (l["position"]["y"] - p["position"]["y"]) ** 2 for p in picks))
        picks.append(far)
        rest.remove(far)
    return picks


def _mode() -> str:
    b = SETTINGS["quick_scan"]
    return ("full survey: every scan position" if b is None else
            f"QUICK SCAN (optional, off by default): {b} positions split across areas by size")


@tool(parse_docstring=True)
def list_scan_positions(building_id: str) -> str:
    """The scan's areas, largest first, with how many positions to read in each, and what the stored survey holds.

    Args:
        building_id: Building slug.
    """
    _check(building_id)
    mp = _mp(building_id)
    areas = _area_table(building_id, mp)
    _call("interior-surveyor", "list_scan_positions", {"building_id": building_id})
    corrected = [i for a in areas for i in a["corrected"]]
    if corrected:
        events.emit("interior-surveyor", "observation",
                    f"Memory: {len(corrected)} position(s) hold assets a person corrected; they will be read again.",
                    refs=corrected)
    total = sum(len(a["locs"]) for a in areas)
    events.emit("interior-surveyor", "observation",
                f"{total} scan positions in {len(areas)} areas ({', '.join(f'{a['id']} {len(a['locs'])}' for a in areas)});"
                f" mode: {_mode()}; stored survey: {_stored(building_id, mp)}.",
                data={"positions": total, "areas": len(areas), "quick_scan": SETTINGS["quick_scan"]})
    rows = [{"id": a["id"], "area": a["name"], "positions": len(a["locs"]), "to_read": a["to_read"]}
            | ({"note": "a person corrected an asset here"} if a["corrected"] else {}) for a in areas]
    return json.dumps({"mode": _mode(), "stored_survey": _stored(building_id, mp), "areas": rows},
                      separators=(",", ":"))


@tool(parse_docstring=True)
def survey_area(building_id: str, area_ids: list[str], reason: str,
                tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """Read one batch: every position still to read in the given areas, with the vision model. Adds to the stored survey.

    Args:
        building_id: Building slug.
        area_ids: Areas in this batch, ids from list_scan_positions (for example ["A1"], or ["A3", "A4", "A5"]).
        reason: Why this batch now, in plain words naming the area (no coordinates or ids).
    """
    _check(building_id)
    st = STATE.setdefault(building_id, {"chosen": [], "batches": 0})
    mp = _mp(building_id)
    areas = {a["id"]: a for a in _area_table(building_id, mp)}
    picked = [areas[str(i).strip().upper()] for i in area_ids or [] if str(i).strip().upper() in areas]
    unknown = [str(i) for i in area_ids or [] if str(i).strip().upper() not in areas]
    st["batches"] = st.get("batches", 0) + 1
    k = st["batches"]
    new = []
    for a in picked:
        left = a["to_read"] - len(a["read"])
        todo = [l for l in a["locs"] if l["id"] not in a["read"]]
        for l in _spread(todo, max(left, 0), a["corrected"]):
            new.append({"location_id": l["id"], "reason": f"batch {k}, {a['name']}: {reason.strip()}"})
    names = " + ".join(f"{a['name']} ({a['id']})" for a in picked) or "nothing"
    total = sum(len(a["locs"]) for a in areas.values())
    _call("interior-surveyor", "survey_area", {"building_id": building_id, "areas": [a["id"] for a in picked]},
          f"survey_area batch {k}: {names}, {len(new)} positions")
    events.emit("interior-surveyor", "decision",
                f"Batch {k}: {names}, {len(new)} of {total} positions ({len(new) / total:.0%} of the scan). "
                f"Why now: {reason.strip()}",
                refs=[c["location_id"] for c in new], data={"batch": k, "areas": [a["id"] for a in picked],
                                                            "positions": len(new)})
    st["chosen"] += new
    try:
        assets = interior.run(building_id, len(new), 0, SETTINGS["cached_positions_only"], chosen=st["chosen"])
    except interior.Stop as e:
        events.emit("interior-surveyor", "observation", f"Survey stopped: {e}")
        return _reply("interior-surveyor", tool_call_id, {"stopped": str(e)[:200]}, {})
    log = json.loads((BUILDINGS / building_id / "survey_log.json").read_text())
    per = {p["location_id"]: p for p in log["positions"]}
    calls = {c["pano"]: c for c in log["calls"] if c["kind"] == "survey"}
    after = {a["id"]: a for a in _area_table(building_id, mp)}
    batch = []
    for a in picked:
        ids = [c["location_id"] for c in new if c["location_id"] in {l["id"] for l in a["locs"]}]
        items = [x for i in ids for x in (per.get(i, {}).get("contents") or [])]
        live = sum(1 for i in ids if not calls.get(i, {}).get("cached"))
        row = {"id": a["id"], "was": a["name"], "seen_as": after[a["id"]]["name"], "positions_read": len(ids),
               "contents_sightings": len(items), "examples": sorted(set(items), key=items.count, reverse=True)[:4],
               "vehicles": sum(per.get(i, {}).get("vehicles", 0) for i in ids)}
        batch.append(row)
        events.emit("interior-surveyor", "observation",
                    f"Batch {k}, {a['name']}: {len(ids)} positions ({len(ids) - live} from cache, {live} live); seen as "
                    f"{'an' if row['seen_as'][:1].lower() in 'aeiou' else 'a'} {row['seen_as']}; {len(items)} contents sightings"
                    + (f" ({', '.join(row['examples'])})" if row["examples"] else "")
                    + (f"; {row['vehicles']} vehicle sightings" if row["vehicles"] else ""), refs=ids, data=row)
    contents = [a for a in buildings.get_assets(building_id) if a["value_basis"] not in ("A-FIN", "V-VEHICLE")]
    value = [sum(a["value_usd_low"] for a in contents), sum(a["value_usd_high"] for a in contents)]
    low = sorted([a for a in contents if a["confidence"] < interior.LOW_CONF], key=lambda a: -a["value_usd_high"])
    stored = _stored(building_id, mp)
    events.emit("interior-surveyor", "observation",
                f"Stored survey now {stored}: {len(contents)} contents assets worth {_usd(value)}; {len(low)} below "
                f"confidence {interior.LOW_CONF}.", refs=[a["id"] for a in low[:6]],
                data={"stored_survey": stored, "contents_assets": len(contents), "value_usd": value})
    left = [{"id": a["id"], "area": a["name"], "positions_left": a["to_read"] - len(a["read"])}
            for a in after.values() if a["to_read"] > len(a["read"])]
    doc = [f"# Interior inventory: {building_id}", "", f"Stored survey: {stored}. Mode this run: {_mode()}.", "",
           "| Id | Room | Asset | Class | Lowest part (ft) | Confidence |", "|---|---|---|---|---|---|"]
    doc += [f"| {a['id']} | {a['room']} | {a['label']} | {a['value_basis']} | {a['height_ft_low']}-{a['height_ft_high']} "
            f"| {a['confidence']} |" for a in assets]
    doc += ["", "## Batches this run", ""] + [f"- {c['location_id'][:6]}: {c['reason']}" for c in st["chosen"]]
    return _reply("interior-surveyor", tool_call_id, {
        "batch": k, "read": batch, "unknown_areas": unknown, "areas_left": left, "stored_survey": stored,
        "contents_assets": len(contents), "contents_value_usd": _usd(value),
        "low_confidence": [f"{a['id']} {a['label'][:40]} conf {a['confidence']}" for a in low[:6]],
        "inventory": f"/dossier/{building_id}/inventory.md"}, {f"/dossier/{building_id}/inventory.md": "\n".join(doc)})


@tool(parse_docstring=True)
def finish_survey(building_id: str) -> str:
    """Finish the interior survey and report the stored survey's exact results to the orchestrator. Call this last.

    Args:
        building_id: Building slug.
    """
    _check(building_id)
    mp = _mp(building_id)
    st = STATE.get(building_id, {"chosen": [], "batches": 0})
    assets = buildings.get_assets(building_id)
    contents = [a for a in assets if a["value_basis"] not in ("A-FIN", "V-VEHICLE")]
    value = [sum(a["value_usd_low"] for a in contents), sum(a["value_usd_high"] for a in contents)]
    low = [a for a in contents if a["confidence"] < interior.LOW_CONF]
    left = [f"{a['name']} ({a['to_read'] - len(a['read'])})" for a in _area_table(building_id, mp)
            if a["to_read"] > len(a["read"])]
    out = {"stored_survey": _stored(building_id, mp), "mode": _mode(),
           "read_this_run": f"{len(st['chosen'])} positions in {st.get('batches', 0)} batch{'' if st.get('batches', 0) == 1 else 'es'}",
           "contents_assets": len(contents), "contents_value_usd": _usd(value),
           "vehicles": sum(1 for a in assets if a["value_basis"] == "V-VEHICLE"),
           "still_low_confidence": len(low), "inventory": f"/dossier/{building_id}/inventory.md"}
    if left:
        out["not_read_this_run"] = left
    events.emit("interior-surveyor", "observation",
                f"Survey finished. Stored survey: {out['stored_survey']} ({out['read_this_run']} this run); "
                f"{out['contents_assets']} contents assets worth {out['contents_value_usd']}, {out['vehicles']} vehicles, "
                f"{len(low)} still below confidence {interior.LOW_CONF}.", data=out)
    return json.dumps(out)


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
def rank_mitigations(building_id: str, depth_ft: float, tool_call_id: Annotated[str, InjectedToolCallId],
                     previous_depth_ft: float | None = None) -> Command:
    """Rank the fixes at a depth by avoided loss per dollar; with previous_depth_ft, also say what moved and why.

    Args:
        building_id: Building slug.
        depth_ft: Interior water depth in feet.
        previous_depth_ft: The depth before the user changed it, if it changed.
    """
    b = _check(building_id)
    d = float(depth_ft)
    _call("mitigation-planner", "rank_mitigations", {"building_id": building_id, "depth_ft": d})
    assets, eps = buildings.get_assets(building_id), buildings.get_entry_points(building_id)
    ms = engine.ranked(building_id, engine.candidates(building_id, assets, eps), assets, d, engine.building_loss_fn(b))
    events.emit("mitigation-planner", "observation",
                f"At {d:g} ft the top fixes are: " + "; ".join(f"{m['rank']}. {m['action']}" for m in ms[:3]),
                refs=[m["id"] for m in ms[:3]], data={"depth_ft": d, "order": [m["id"] for m in ms]})
    changes = []
    if previous_depth_ft is not None and float(previous_depth_ft) != d:
        pd = float(previous_depth_ft)
        old = {m["id"]: m for m in engine.ranked(building_id, engine.candidates(building_id, assets, eps), assets, pd,
                                                 engine.building_loss_fn(b))}
        for m in ms[:5]:
            o = old.get(m["id"])
            if o and o["rank"] != m["rank"]:
                why = (f"avoided loss {_usd([o['avoided_loss_usd_low'], o['avoided_loss_usd_high']])} at {pd:g} ft -> "
                       f"{_usd([m['avoided_loss_usd_low'], m['avoided_loss_usd_high']])} at {d:g} ft")
                changes.append(f"{m['action']}: rank {o['rank']} -> {m['rank']} ({why})")
        for m in old.values():
            if m["rank"] <= 3 and next(x["rank"] for x in ms if x["id"] == m["id"]) > 3:
                why = (f"a {m['action'].split(' ft')[0].split()[-1]} ft barrier stops helping once water is deeper"
                       if m["kind"] == "entry_barrier" else "it avoids less per dollar at this depth")
                changes.append(f"Dropped out of the top 3: {m['action']} (was {m['rank']}; {why})")
        if changes:
            events.emit("mitigation-planner", "decision", f"Priority change {pd:g} -> {d:g} ft: " + "; ".join(changes[:3]),
                        data={"from_ft": pd, "to_ft": d, "changes": changes})
    doc = [f"# Mitigations at {d:g} ft: {building_id}", "", "| Rank | Action | Cost | Avoided loss | Note |",
           "|---|---|---|---|---|"]
    doc += [f"| {m['rank']} | {m['action']} | {_usd([m['cost_usd_low'], m['cost_usd_high']])} | "
            f"{_usd([m['avoided_loss_usd_low'], m['avoided_loss_usd_high']])} | {m['payback_note']} |" for m in ms]
    path = f"/dossier/{building_id}/mitigations-{d:g}ft.md"
    return _reply("mitigation-planner", tool_call_id, {
        "depth_ft": d, "top": [f"{m['rank']}. {m['action']} (cost {_usd([m['cost_usd_low'], m['cost_usd_high']])}, "
                               f"avoids {_usd([m['avoided_loss_usd_low'], m['avoided_loss_usd_high']])})" for m in ms[:3]],
        "changed_since_previous_depth": changes[:4], "details": path}, {path: "\n".join(doc)})


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
    src = guard.numbers(guard.document_sources(b, assets, d))
    files = {f"/dossier/{building_id}/report.html":
             guard.guarded(report_html.render(b, assets, eps, d), src, "the report", "communications"),
             f"/dossier/{building_id}/playbook.html":
             guard.guarded(playbook_html.render(b, assets, eps, d), src, "the playbook", "communications")}
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
    assets = buildings.get_assets(building_id)
    html = guard.guarded(playbook_html.render(b, assets, buildings.get_entry_points(building_id), d),
                         guard.document_sources(b, assets, d), "the playbook being sent", "communications")
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
                f"to {len(done)} similar asset{'s' if len(done) != 1 else ''}"
                + (f" ({', '.join(done)})" if done else "") + f": {reason}", refs=done,
                data={"correction_id": correction_id, "applied_to": done})
    return json.dumps({"applied_to": done})


ROLE_TOOLS = {
    "site-scout": [find_entry_points],
    "interior-surveyor": [list_scan_positions, survey_area, relook_asset, finish_survey],
    "market-analyst": [get_building_value],
    "scenario-builder": [run_scenario],
    "mitigation-planner": [rank_mitigations],
    "communications": [draft_documents],
}
ORCHESTRATOR_TOOLS = [get_corrections, apply_correction_to_similar, send_playbook]
# A subagent's job ends with one of these; its exact result becomes the subagent's reply (subagents.EchoFinalTool).
FINAL_TOOLS = {"find_entry_points", "get_building_value", "run_scenario", "rank_mitigations", "draft_documents",
               "finish_survey"}
