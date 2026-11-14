"""The agent's tools: thin, traced wrappers over the real Waterline functions (no fake data).

Each tool belongs to one subagent (ROLE) and emits its own AgentEvents: a tool_call when it starts and an
observation (or decision) with what it found, including whether a result came from the cache.
In demo mode (SETTINGS["cached_positions_only"]) the interior survey offers only scan positions whose vision
answers are already cached, so a run costs model calls for the agent's reasoning only.
"""
import json
import os

from langchain_core.tools import tool

from app import buildings, corrections
from app.actions import playbook as playbook_html
from app.actions import report as report_html
from app.agent import events, memory
from app.config import BUILDINGS, CACHE
from app.loss import mitigations as engine
from app.loss import model
from app.sources import gemini
from app.sources.cache import write_json
from app.survey import interior, site

SETTINGS = {"cached_positions_only": True, "max_positions": 20}
DOSSIER = CACHE / "agent" / "dossier"


def _call(role: str, name: str, args: dict, text: str | None = None) -> None:
    events.emit(role, "tool_call", text or f"{name}({', '.join(f'{k}={v}' for k, v in args.items())})",
                data={"tool": name, "args": args})


def _check(building_id: str) -> dict:
    if building_id not in buildings.building_ids():
        raise ValueError(f"unknown building {building_id}")
    return buildings.get_building(building_id)


# ------------------------------------------------------------------ site-scout

@tool(parse_docstring=True)
def get_site_context(building_id: str) -> str:
    """Flood and site context for a building: FEMA zone, ground elevation, CoStar door counts, aerial capture.

    Args:
        building_id: Building slug, for example building-e.
    """
    b = _check(building_id)
    _call("site-scout", "get_site_context", {"building_id": building_id})
    out = {k: b.get(k) for k in ("flood_zone", "flood_zone_subtype", "in_mapped_flood_zone", "ground_elevation_ft",
                                 "drive_in_bays", "loading_docks_external", "aerial_collection", "aerial_capture_date",
                                 "property_type", "property_subtype", "size_sqft", "scan_coverage")}
    events.emit("site-scout", "observation",
                f"FEMA zone {out['flood_zone']} ({'inside' if out['in_mapped_flood_zone'] else 'outside'} the 1% "
                f"annual-chance area); ground {out['ground_elevation_ft']} ft (context only); CoStar: "
                f"{out['drive_in_bays']} drive-in bays, {out['loading_docks_external']} docks.", data=out)
    return json.dumps(out)


@tool(parse_docstring=True)
def find_entry_points(building_id: str) -> str:
    """Find where water gets in from the Vexcel aerial images (ortho and obliques), ranked, checked against CoStar.

    Args:
        building_id: Building slug.
    """
    _check(building_id)
    _call("site-scout", "find_entry_points", {"building_id": building_id},
          "find_entry_points on the ortho and oblique aerial images")
    eps, log = site.scout(building_id, cache_only=SETTINGS["cached_positions_only"]
                          and (BUILDINGS / building_id / "site_log.json").exists())
    src = "from cache" if log["cached"] else f"live ({log['model']})"
    events.emit("site-scout", "observation",
                f"{len(eps)} entry points ({src}): " + "; ".join(f"{e['id']} {e['kind']}" for e in eps[:6])
                + f". Count check: {log['count_check']}.", refs=[e["id"] for e in eps], data={"cached": log["cached"]})
    return json.dumps({"entry_points": [{k: e[k] for k in ("id", "kind", "image_kind", "confidence", "evidence")}
                                        for e in eps], "count_check": log["count_check"], "from_cache": log["cached"]})


# ------------------------------------------------------------------ interior-surveyor

def _cached_location_ids(bid: str, mp: dict) -> set[str]:
    """Positions with a cached vision answer (data/cache/buildings/<id>/vision_index.json, kept by the survey)."""
    return interior.vision_index(bid)


@tool(parse_docstring=True)
def list_scan_positions(building_id: str) -> str:
    """List the Matterport scan positions you can inspect, grouped by room, with floor-plan coordinates in metres.

    Args:
        building_id: Building slug.
    """
    _check(building_id)
    mp = json.loads((BUILDINGS / building_id / "parts.json").read_text())["matterport"]
    rooms = {r["id"]: (r.get("label") or "") for r in mp["rooms"]}
    cached = _cached_location_ids(building_id, mp)
    with_pano = {p["location_id"] for p in mp["panos"]}
    offer = [l for l in mp["locations"] if l["id"] in with_pano and
             (not SETTINGS["cached_positions_only"] or l["id"] in cached)]
    _call("interior-surveyor", "list_scan_positions", {"building_id": building_id})
    by_room: dict[str, list] = {}
    for l in offer:
        rid = (l.get("room") or {}).get("id") or "none"
        by_room.setdefault(rooms.get(rid) or f"room {rid[:6]}", []).append(
            {"location_id": l["id"], "x": round(l["position"]["x"], 1), "y": round(l["position"]["y"], 1)})
    note = (f"{len(offer)} of {len(with_pano)} positions offered: demo mode offers only positions whose vision answers "
            "are cached, so inspecting them costs nothing" if SETTINGS["cached_positions_only"]
            else f"all {len(offer)} positions offered; uncached ones cost one vision call each")
    events.emit("interior-surveyor", "observation", f"{len(with_pano)} scan positions in {len(by_room)} rooms; {note}.",
                data={"rooms": {k: len(v) for k, v in by_room.items()}})
    return json.dumps({"note": note, "max_positions": SETTINGS["max_positions"], "rooms": by_room})


@tool(parse_docstring=True)
def survey_positions(building_id: str, choices: list[dict]) -> str:
    """Inspect the chosen scan positions with the vision model and build the asset inventory with heights from the 3D mesh.

    Args:
        building_id: Building slug.
        choices: The positions to inspect, each {"location_id": "...", "reason": "why this position"}. At most 20.
    """
    _check(building_id)
    choices = [c for c in choices if isinstance(c, dict) and c.get("location_id")][:SETTINGS["max_positions"]]
    _call("interior-surveyor", "survey_positions", {"building_id": building_id, "positions": len(choices)},
          f"survey_positions on {len(choices)} chosen scan positions")
    for c in choices:
        events.emit("interior-surveyor", "decision", f"Inspect position {c['location_id'][:8]}: {c.get('reason', '')}",
                    refs=[c["location_id"]])
    backup = BUILDINGS / building_id / "assets_batch.json"
    if not backup.exists() and (BUILDINGS / building_id / "assets.json").exists():
        backup.write_text((BUILDINGS / building_id / "assets.json").read_text())
    try:
        assets = interior.run(building_id, SETTINGS["max_positions"], 0, SETTINGS["cached_positions_only"],
                              chosen=[{"location_id": c["location_id"], "reason": c.get("reason", "")} for c in choices])
    except interior.Stop as e:
        events.emit("interior-surveyor", "observation", f"Survey stopped: {e}")
        return json.dumps({"stopped": str(e)})
    log = json.loads((BUILDINGS / building_id / "survey_log.json").read_text())
    calls = log["calls"]
    n_cached = sum(1 for c in calls if c.get("cached"))
    skipped = [p["location_id"] for p in log["positions"] if p.get("error")]
    low = sorted([a for a in assets if a["confidence"] < interior.LOW_CONF and a["value_basis"] != "A-FIN"],
                 key=lambda a: a["confidence"])
    by_class: dict[str, int] = {}
    for a in assets:
        by_class[a["value_basis"]] = by_class.get(a["value_basis"], 0) + 1
    events.emit("interior-surveyor", "observation",
                f"{len(assets)} assets from {len(calls)} positions ({n_cached} vision answers from cache, "
                f"{len(calls) - n_cached} live); {len(low)} below confidence {interior.LOW_CONF}"
                + (f"; skipped {len(skipped)} uncached positions" if skipped else ""),
                refs=[a["id"] for a in low[:10]], data={"by_class": by_class, "cached_calls": n_cached,
                                                       "live_calls": len(calls) - n_cached})
    return json.dumps({"assets": len(assets), "by_value_class": by_class, "vision_calls_from_cache": n_cached,
                       "live_vision_calls": len(calls) - n_cached, "skipped_positions": skipped,
                       "low_confidence": [{"asset_id": a["id"], "label": a["label"], "room": a["room"],
                                           "height_ft": [a["height_ft_low"], a["height_ft_high"]],
                                           "confidence": a["confidence"]} for a in low[:12]]})


@tool(parse_docstring=True)
def relook_asset(building_id: str, asset_id: str) -> str:
    """Look again at a low-confidence asset from the nearest neighbouring scan position; updates the record if the new view is more confident.

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
    except (gemini.BillingError, Exception) as e:   # budget or billing stop: report, do not crash the run
        events.emit("interior-surveyor", "observation", f"Re-look of {asset_id} failed: {e}", refs=[asset_id])
        return json.dumps({"error": str(e)[:300]})
    b, a = r["before"], r["after"]
    src = "from cache" if r["cached"] else f"live ({r['model']})" if r["model"] else "no call"
    events.emit("interior-surveyor", "observation",
                f"Re-looked '{r['label']}' from neighbouring position {str(r['neighbour_location_id'])[:8]} ({src}): "
                f"height {b['height_ft_low']}-{b['height_ft_high']} ft at confidence {b['confidence']} -> "
                f"{a['height_ft_low']}-{a['height_ft_high']} ft at {a['confidence']}; {r['result']}.",
                refs=[asset_id] + ([r["neighbour_location_id"]] if r["neighbour_location_id"] else []), data=r)
    return json.dumps(r)


# ------------------------------------------------------------------ market-analyst

@tool(parse_docstring=True)
def get_building_value(building_id: str) -> str:
    """CoStar building data behind the loss: property type, size, year built, tenants, assessor improvement value, scan coverage.

    Args:
        building_id: Building slug.
    """
    b = _check(building_id)
    _call("market-analyst", "get_building_value", {"building_id": building_id})
    occ = model.occupancy_for(b)
    out = {k: b.get(k) for k in ("property_type", "property_subtype", "size_sqft", "year_built", "improvement_value_usd",
                                 "value_as_of", "value_source", "scan_coverage", "scan_area_sqft")}
    out["tenants"] = len(b.get("tenants") or [])
    out["structure_basis_usd"] = model.structure_basis(b)
    out["hazus_occupancy"] = occ
    events.emit("market-analyst", "observation",
                f"{out['property_subtype']}, {out['size_sqft']:,.0f} sq ft, built {out['year_built']}; assessor "
                f"improvement value ${out['improvement_value_usd']:,.0f} x scan coverage {out['scan_coverage']:.0%} = "
                f"structure basis ${out['structure_basis_usd']:,.0f}; Hazus occupancy {occ}.", data=out)
    return json.dumps(out)


# ------------------------------------------------------------------ scenario-builder

@tool(parse_docstring=True)
def run_scenario(building_id: str, depth_ft: float) -> str:
    """Price the loss for a water depth above the ground-floor slab (0 to 8 ft): contents, structure, assets hit.

    Args:
        building_id: Building slug.
        depth_ft: Interior water depth in feet (a scenario the user chose, not a forecast).
    """
    b = _check(building_id)
    _call("scenario-builder", "run_scenario", {"building_id": building_id, "depth_ft": depth_ft})
    assets = buildings.get_assets(building_id)
    s = model.scenario(b, assets, float(depth_ft))
    by_id = {a["id"]: a for a in assets}
    spans = model._spans(assets)
    top = sorted(assets, key=lambda a: -a["value_usd_high"] * model.fractions(a, float(depth_ft), spans.get(a["id"]))[1])[:5]
    movable = [a for a in assets if a["value_basis"] == "V-VEHICLE" and float(depth_ft) >= a["height_ft_low"]]
    out = {"depth_ft": depth_ft, "contents_usd": [s["loss_usd_low"], s["loss_usd_high"]],
           "structure_usd": [s["structure_loss_usd_low"], s["structure_loss_usd_high"]],
           "total_usd": [s["loss_usd_low"] + s["structure_loss_usd_low"], s["loss_usd_high"] + s["structure_loss_usd_high"]],
           "likely": sum(1 for h in s["assets_hit"] if h["status"] == "likely"),
           "possible": sum(1 for h in s["assets_hit"] if h["status"] == "possible"),
           "top_assets": [{"asset_id": a["id"], "label": by_id[a["id"]]["label"], "value_basis": a["value_basis"]} for a in top],
           "movable_assets_at_risk": len(movable),
           "assumptions": [{"id": x["id"], "placeholder": x["placeholder"]} for x in s["assumptions"]]}
    events.emit("scenario-builder", "observation",
                f"At {depth_ft:g} ft: contents ${out['contents_usd'][0]:,}-{out['contents_usd'][1]:,}, structure "
                f"${out['structure_usd'][0]:,}-{out['structure_usd'][1]:,}, total ${out['total_usd'][0]:,}-"
                f"{out['total_usd'][1]:,}; {out['likely']} assets likely hit, {out['possible']} possible; "
                f"{len(movable)} vehicles at risk.", refs=[a["asset_id"] for a in out["top_assets"]], data=out)
    return json.dumps(out)


# ------------------------------------------------------------------ mitigation-planner

@tool(parse_docstring=True)
def rank_mitigations(building_id: str, depth_ft: float) -> str:
    """Rank the fixes at a depth by avoided loss per dollar: cost, avoided loss, payback note.

    Args:
        building_id: Building slug.
        depth_ft: Interior water depth in feet.
    """
    b = _check(building_id)
    _call("mitigation-planner", "rank_mitigations", {"building_id": building_id, "depth_ft": depth_ft})
    assets, eps = buildings.get_assets(building_id), buildings.get_entry_points(building_id)
    ms = engine.ranked(building_id, engine.candidates(building_id, assets, eps), assets, float(depth_ft),
                       engine.building_loss_fn(b))
    top = [{k: m[k] for k in ("id", "rank", "kind", "action", "cost_usd_low", "cost_usd_high", "avoided_loss_usd_low",
                              "avoided_loss_usd_high", "payback_note")} for m in ms[:6]]
    events.emit("mitigation-planner", "observation",
                f"At {depth_ft:g} ft the top fixes are: " + "; ".join(f"{m['rank']}. {m['action']}" for m in top[:3]),
                refs=[m["id"] for m in top], data={"depth_ft": depth_ft, "order": [m["id"] for m in ms]})
    return json.dumps({"depth_ft": depth_ft, "ranked": top, "total_candidates": len(ms)})


# ------------------------------------------------------------------ communications

@tool(parse_docstring=True)
def draft_documents(building_id: str, depth_ft: float) -> str:
    """Render the resilience report and the room-by-room pre-storm playbook for a depth; returns where they are.

    Args:
        building_id: Building slug.
        depth_ft: Interior water depth in feet the documents are planned for.
    """
    b = _check(building_id)
    _call("communications", "draft_documents", {"building_id": building_id, "depth_ft": depth_ft})
    assets, eps = buildings.get_assets(building_id), buildings.get_entry_points(building_id)
    out = DOSSIER / building_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.html").write_text(report_html.render(b, assets, eps, float(depth_ft)))
    (out / "playbook.html").write_text(playbook_html.render(b, assets, eps, float(depth_ft)))
    urls = {"report": f"/buildings/{building_id}/report?depth_ft={depth_ft:g}",
            "playbook": f"/buildings/{building_id}/playbook?depth_ft={depth_ft:g}"}
    events.emit("communications", "artifact", f"Drafted the resilience report and the pre-storm playbook for {depth_ft:g} ft.",
                refs=list(urls.values()), data=urls)
    return json.dumps(urls)


@tool(parse_docstring=True)
def send_playbook(building_id: str, recipient: str, depth_ft: float) -> str:
    """Send the pre-storm playbook. A person must approve this call before it runs.

    Args:
        building_id: Building slug.
        recipient: Email address; must be in ALLOWED_RECIPIENTS.
        depth_ft: Depth the playbook was drafted for.
    """
    _check(building_id)
    allowed = {a.strip().lower() for a in os.environ.get("ALLOWED_RECIPIENTS", "").split(",") if a.strip()}
    r = recipient.strip().lower()
    out = {"building_id": building_id, "recipient": r, "depth_ft": depth_ft, "approved": True}
    if r not in allowed:
        out.update(status="refused", reason="recipient is not in ALLOWED_RECIPIENTS")
    else:
        out.update(status="not_sent", reason="Approved and recorded; email delivery is built in Phase 5B, so nothing "
                                             "left this machine.")
    sent = DOSSIER / building_id / "sends.json"
    log = json.loads(sent.read_text()) if sent.exists() else []
    write_json(sent, log + [out])
    events.emit("communications", "observation", f"Approved send to {r}: {out['status']} ({out['reason']})", data=out)
    return json.dumps(out)


# ------------------------------------------------------------------ orchestrator: memory of human corrections

@tool(parse_docstring=True)
def get_corrections(building_id: str) -> str:
    """Read the human corrections saved for this building (the agent's long-term memory).

    Args:
        building_id: Building slug.
    """
    _check(building_id)
    text = memory.read_corrections(building_id)
    recs = corrections.load(building_id)
    _call("orchestrator", "get_corrections", {"building_id": building_id},
          f"Read {memory.agent_path(building_id)} ({len(recs)} corrections)")
    current = buildings.get_assets(building_id)
    by_id = {a["id"]: a for a in current}
    sugg = []
    for rec in recs:
        if rec["by"] != "human" or rec["action"] != "patch" or rec["asset_id"] not in by_id:
            continue
        done = {x["asset_id"] for x in recs if x.get("propagated_from") == rec["id"]}
        sim = [a["id"] for a in corrections.similar(current, by_id[rec["asset_id"]]) if a["id"] not in done
               and a["source"] == "vision"]
        if sim:
            sugg.append({"correction_id": rec["id"], "asset_id": rec["asset_id"], "changes": rec["changes"],
                         "similar_asset_ids": sim})
    return json.dumps({"memory": text or "(no corrections yet)", "corrections": len(recs), "propagate_candidates": sugg})


@tool(parse_docstring=True)
def apply_correction_to_similar(building_id: str, correction_id: str, asset_ids: list[str], reason: str) -> str:
    """Apply a human correction to similar assets in the same building, recorded as propagated by the agent.

    Args:
        building_id: Building slug.
        correction_id: The human correction to copy.
        asset_ids: Similar assets to apply it to.
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
        try:
            corrections.record(building_id, buildings.get_assets(building_id), aid, "patch", dict(src["changes"]),
                               note=reason, by="agent", propagated_from=correction_id)
            done.append(aid)
        except (KeyError, corrections.CorrectionError):
            continue
    events.emit("orchestrator", "decision",
                f"Applied human correction {correction_id} ({src['changes']}) to {len(done)} similar assets: {reason}",
                refs=done, data={"correction_id": correction_id})
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
