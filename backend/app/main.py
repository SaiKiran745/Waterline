"""Waterline API (AGENTS.md section 8; contracts/ v1.1.0).

Real buildings come from data/cache/ (built by `python -m app.sources.pull`); ids are slugs ("building-a").
`fixture-1` is the FIXTURE building from contracts/fixtures/ and supports every endpoint.

Run: uvicorn app.main:app --host 127.0.0.1 --port 8000
"""
import json
import mimetypes
from datetime import datetime, timezone
import os
import re

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from app import buildings, corrections, fixtures
from app.actions import playbook as playbook_html
from app.actions import report as report_html
from app.actions import send as send_action
from app.agent import events as agent_events
from app.agent import guard
from app.agent import service as agent_service
from app.agent.replay import last_run, replay
from app.config import BUILDINGS, FRONTEND_ORIGINS, MEDIA, demo_mode
from app.loss import mitigations as engine
from app.loss import model, rank
from app.sources.cache import CacheMiss

app = FastAPI(title="Waterline API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_methods=["GET", "POST", "PATCH", "DELETE"],
                   allow_headers=["Content-Type"])

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
FIX = fixtures.FIXTURE_ID
FACE_PATH = re.compile(r"^([a-z0-9-]+)/panos/([A-Za-z0-9]+)/face([0-5])\.jpg$")
mimetypes.add_type("text/plain", ".obj")


@app.exception_handler(CacheMiss)
async def cache_miss(_: Request, exc: CacheMiss):
    return JSONResponse(status_code=503, content={"detail": str(exc), "demo_mode": demo_mode()})


def _real(bid: str) -> dict:
    if bid not in buildings.building_ids():
        raise HTTPException(404, f"unknown building {bid}")
    return buildings.get_building(bid)


@app.get("/health")
def health():
    return {"ok": True, "demo_mode": demo_mode()}


@app.get("/buildings")
def list_buildings(fixture: int = 0):
    """Buildings ranked by precomputed median total loss at 2 ft (contracts v1.3), then by letter. ?fixture=1 for FIXTURE data."""
    if fixture:
        return [fixtures.building()]
    r = rank.load()
    return sorted(buildings.list_buildings(), key=lambda b: (-(r.get(b["id"], {}).get("2", {}).get("total_median", 0)), b["id"]))


@app.get("/triage")
def triage(depth_ft: int = Query(2), fixture: int = 0):
    """Triage ranking (contracts v1.3): every building ranked by median total loss at 1, 2, 4 or 6 ft, each labelled
    "surveyed" (with positions read and contents count) or "structure only"."""
    if str(depth_ft) not in map(str, rank.DEPTHS):
        raise HTTPException(422, f"depth_ft must be one of {list(rank.DEPTHS)}")
    if fixture:
        return fixtures.triage()
    rows = rank.triage(str(depth_ft))
    if not rows:
        raise HTTPException(503, "no triage ranking yet: run python -m app.loss.rank")
    return rows


@app.get("/buildings/{bid}")
def get_building(bid: str):
    if bid == FIX:
        return fixtures.detail()
    b = _real(bid)
    return {"building": b, "entry_points": buildings.get_entry_points(bid), "assets": buildings.get_assets(bid)}


@app.get("/buildings/{bid}/scenario")
def scenario(bid: str, depth_ft: float = Query(..., ge=0, le=8)):
    if bid == FIX:
        return fixtures.scenario(depth_ft)
    return model.scenario(_real(bid), buildings.get_assets(bid), depth_ft)


@app.get("/buildings/{bid}/scenario_table")
def scenario_table(bid: str):
    """Every slider step, 0 to 8 ft by 0.25 ft, with each asset's damage fraction per step (contracts v1.2)."""
    if bid == FIX:
        return fixtures.scenario_table()
    return model.scenario_table(_real(bid), buildings.get_assets(bid))


@app.get("/buildings/{bid}/grounding")
def grounding(bid: str):
    """Scenario grounding (contracts v1.3): floor elevation, the outside water surface for each slider step, and
    reference levels (FEMA 1% flood level, lowest door ground), all in ft NAVD 88. Precomputed, read from cache."""
    if bid == FIX:
        return fixtures.grounding()
    _real(bid)
    from app.loss import grounding as ground
    g = ground.load(bid)
    if g is None:
        raise HTTPException(503, "no grounding yet: run python -m app.loss.grounding")
    return g


@app.get("/buildings/{bid}/mitigations")
def mitigations(bid: str, depth_ft: float = Query(2, ge=0, le=8)):
    """Ranked at exactly the requested depth; mitigation ids are stable across depths."""
    if bid == FIX:
        return fixtures.mitigations(depth_ft)
    b = _real(bid)
    assets, eps = buildings.get_assets(bid), buildings.get_entry_points(bid)
    return engine.ranked(bid, engine.candidates(bid, assets, eps), assets, depth_ft, engine.building_loss_fn(b))


# ---------------------------------------------------------------- human corrections

def _assets_for(bid: str) -> list[dict]:
    if bid == FIX:
        return fixtures.assets()
    _real(bid)
    return buildings.get_assets(bid)


def _correct(bid: str, asset_id: str, action: str, body: dict, depth_ft: float) -> dict:
    body = dict(body or {})
    note = body.pop("note", None)
    current = _assets_for(bid)
    try:
        rec = corrections.record(bid, current, asset_id, action, body if action == "patch" else None, note)
    except KeyError:
        raise HTTPException(404, f"unknown asset {asset_id} in {bid}")
    except corrections.CorrectionError as e:
        raise HTTPException(422, str(e))
    after = _assets_for(bid)
    asset = next((a for a in after if a["id"] == asset_id), None)
    if bid != FIX:
        rank.compute()                               # keep the triage ranking in step with the correction
    similar = corrections.similar(after, asset or next(a for a in current if a["id"] == asset_id))
    return {"correction": rec, "asset": asset,
            "similar_asset_ids": [a["id"] for a in similar],
            "scenario": scenario(bid, depth_ft), "mitigations": mitigations(bid, depth_ft)}


@app.patch("/buildings/{bid}/assets/{asset_id}")
def patch_asset(bid: str, asset_id: str, body: dict = Body(...), depth_ft: float = Query(2, ge=0, le=8)):
    """Human correction. Body: any of label, category, height_ft_low, height_ft_high, room, plus an optional note.
    Saved, applied on every read, written to the agent's memory; returns the new scenario and mitigations."""
    return _correct(bid, asset_id, "patch", body, depth_ft)


@app.delete("/buildings/{bid}/assets/{asset_id}")
def delete_asset(bid: str, asset_id: str, body: dict | None = Body(default=None),
                 depth_ft: float = Query(2, ge=0, le=8)):
    """Human removes a wrong asset (optional body {"note": ...}). Same effects as PATCH."""
    return _correct(bid, asset_id, "delete", body or {}, depth_ft)


def agent_tools_dossier():
    from app.config import CACHE
    return CACHE / "agent" / "dossier"


def _sse(gen):
    return StreamingResponse(gen, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _recipient(body: dict) -> str:
    allowed = [a.strip() for a in os.environ.get("ALLOWED_RECIPIENTS", "").split(",") if a.strip()]
    r = str(body.get("recipient") or (allowed[0] if allowed else "")).strip()
    if r.lower() not in {a.lower() for a in allowed}:
        raise HTTPException(403, "recipient is not in ALLOWED_RECIPIENTS")
    return r


@app.post("/buildings/{bid}/run")
def run(bid: str, body: dict | None = Body(default=None)):
    """Starts the live agent (turn 1: assess at depth_ft, default 1). FIXTURE: trace replay.
    {"replay": true}, or DEMO_MODE=1 without {"live": true}: "Replay last run", the saved trace, labelled as a replay
    (in DEMO_MODE the pinned demo run, see app/demo.py). The interior survey reads every scan position."""
    body = body or {}
    if bid == FIX:
        return {"status": "replay", "building_id": bid, "depth_ft": body.get("depth_ft"),
                "events_url": f"/buildings/{bid}/events", "note": "FIXTURE trace replay"}
    _real(bid)
    if body.get("replay") or (demo_mode() and not body.get("live")):
        info = _replay_info(bid)
        if demo_mode():                              # the replayed run's outcome, so the UI's numbers match its trace
            from app import demo
            info["outcome_applied"] = demo.apply_replay_outcome(bid)
        return info
    try:
        return agent_service.start(bid, float(body.get("depth_ft", 1)))
    except agent_service.Busy as e:
        raise HTTPException(409, str(e))


@app.post("/buildings/{bid}/depth")
def change_depth(bid: str, body: dict = Body(...)):
    """The user moved the slider during a session: the agent re-plans, re-prices and re-ranks (turn 2).
    Body: {"depth_ft": 4}."""
    _real(bid)
    try:
        return agent_service.change_depth(bid, float(body["depth_ft"]), _recipient(body))
    except KeyError:
        raise HTTPException(409, "no agent session for this building: POST /run first")
    except agent_service.Busy as e:
        raise HTTPException(409, str(e))


@app.post("/buildings/{bid}/request_send")
def request_send(bid: str, body: dict | None = Body(default=None)):
    """The agent drafts the report and playbook and calls send_playbook, which waits for POST /send (turn 3)."""
    _real(bid)
    try:
        return agent_service.request_send(bid, _recipient(body or {}))
    except KeyError:
        raise HTTPException(409, "no agent session for this building: POST /run first")
    except agent_service.Busy as e:
        raise HTTPException(409, str(e))


@app.get("/buildings/{bid}/agent")
def agent_status(bid: str):
    _real(bid)
    return agent_service.status(bid)


def _replay_info(bid: str) -> dict:
    r = last_run(bid)
    if r is None:
        raise HTTPException(404, "no saved agent run for this building to replay")
    return {"status": "replay", **{k: v for k, v in r.items() if not k.startswith("_")},
            "events_url": f"/buildings/{bid}/events?replay=1"}


def _local(request: Request) -> None:
    if (request.client.host if request.client else "") not in LOCAL_HOSTS:
        raise HTTPException(403, "localhost only")


@app.post("/demo/reset")
def demo_reset(request: Request):
    """Put the demo in its known starting state (app/demo.py): full stored surveys, exactly one human correction on
    E, no agent session, depth 1 ft. From cache, no model calls; safe to repeat. Localhost only."""
    _local(request)
    from app import demo
    try:
        agent_service.clear()
    except agent_service.Busy as e:
        raise HTTPException(409, str(e))
    try:
        return demo.reset()
    except demo.DemoError as e:
        raise HTTPException(409, str(e))


@app.get("/demo/state")
def demo_state():
    """The starting state the last reset set (depth_ft 1, positions read and corrections per building)."""
    from app import demo
    return demo.state()


@app.get("/buildings/{bid}/runs/latest")
def latest_run(bid: str):
    """The last saved agent run (for "Replay last run"): run id, when it was recorded, time, cost, turns."""
    _real(bid)
    return _replay_info(bid)


@app.get("/buildings/{bid}/events")
def events(request: Request, bid: str, speed: float = Query(1.0, ge=0, le=100),
           replay_: int = Query(0, alias="replay"), after: int = Query(-1, ge=-1)):
    """Live trace while the agent runs; otherwise (or with ?replay=1) the last saved run, sent as a replay: a first
    "replay" event carries the label, and "end" repeats it. FIXTURE: fixture trace.
    Live: ?after=<event id> (or the Last-Event-ID header a reconnecting EventSource sends) skips events already seen."""
    if bid == FIX:
        return _sse(replay(fixtures.load("agent_events.json"), speed))
    _real(bid)
    if agent_service.has_live(bid) and not replay_:
        last = request.headers.get("last-event-id", "")
        seen = max(after, int(last) if last.isdigit() else -1)
        return _sse(agent_service.live(bid, after=seen))
    r = last_run(bid)
    if r is None:
        raise HTTPException(404, "no agent run for this building yet: POST /run")
    label = {k: v for k, v in r.items() if not k.startswith("_")}
    return _sse(replay(r["_events"], speed, label=label))


@app.get("/buildings/{bid}/report", response_class=HTMLResponse)
def report(bid: str, depth_ft: float = Query(2, ge=0, le=8)):
    if bid == FIX:
        return fixtures.report_html()
    b, assets = _real(bid), buildings.get_assets(bid)
    return guard.guarded(report_html.render(b, assets, buildings.get_entry_points(bid), depth_ft),
                         guard.document_sources(b, assets, depth_ft), "the report")


@app.get("/buildings/{bid}/playbook", response_class=HTMLResponse)
def playbook(bid: str, depth_ft: float = Query(2, ge=0, le=8)):
    if bid == FIX:
        return fixtures.playbook_html()
    b, assets = _real(bid), buildings.get_assets(bid)
    return guard.guarded(playbook_html.render(b, assets, buildings.get_entry_points(bid), depth_ft),
                         guard.document_sources(b, assets, depth_ft), "the playbook")


@app.post("/buildings/{bid}/send")
def send(bid: str, body: dict = Body(...), depth_ft: float = Query(2, ge=0, le=8)):
    """{"approved": true, "recipient": "<in ALLOWED_RECIPIENTS>"}. With an agent waiting for approval this resumes it
    (false rejects); otherwise it sends the playbook directly. Email goes out over SMTP when SMTP_* and EMAIL_FROM are
    set; otherwise the status is "draft_only" (draft only, not sent)."""
    if bid != FIX:
        _real(bid)
    if bid != FIX and agent_service.waiting_for_approval(bid) and body.get("approved") is False:
        return agent_service.decide(bid, False, str(body.get("note") or ""))
    if body.get("approved") is not True:
        raise HTTPException(400, 'sending requires {"approved": true}')
    recipient = _recipient(body).lower()             # defaults to the first allowed address; 403 if not allowed
    if bid != FIX and agent_service.waiting_for_approval(bid):
        return agent_service.decide(bid, True)      # resumes the agent; its send_playbook tool sends
    if bid == FIX:
        html = fixtures.playbook_html()
    else:
        b, assets = _real(bid), buildings.get_assets(bid)
        html = guard.guarded(playbook_html.render(b, assets, buildings.get_entry_points(bid), depth_ft),
                             guard.document_sources(b, assets, depth_ft), "the playbook being sent")
    return send_action.send_playbook(bid, recipient, depth_ft, html, approved=True)


@app.get("/buildings/{bid}/dossier")
def dossier(bid: str):
    """The agent's dossier for a building: every file it wrote (notes, inventory, scenarios, mitigations, report,
    playbook, send log) with its contents."""
    if bid != FIX:
        _real(bid)
    root = agent_tools_dossier() / bid
    files = []
    if root.exists():
        for f in sorted(root.rglob("*")):
            if f.is_file():
                st = f.stat()
                files.append({"path": f"/dossier/{bid}/{f.relative_to(root)}", "bytes": st.st_size,
                              "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                              "content": f.read_text(errors="replace")})
    return {"building_id": bid, "files": files}


# ---------------------------------------------------------------- media

def _screening(bid: str) -> dict:
    path = BUILDINGS / bid / "screening.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _face_clear(bid: str, pano_id: str, face: int) -> bool:
    return bool(_screening(bid).get(f"{pano_id}/face{face}", {}).get("clear"))


def manifest(bid: str) -> dict:
    idx_path = BUILDINGS / bid / "media_index.json"
    if not idx_path.exists():
        raise CacheMiss(f"no media index for {bid}: run `python -m app.sources.pull`")
    idx = json.loads(idx_path.read_text())
    scr = _screening(bid)
    panos, shown = [], 0
    for p in idx["panos"]:
        faces = {str(i): url for i, url in enumerate(p["faces"]) if scr.get(f"{p['id']}/face{i}", {}).get("clear")}
        shown += len(faces)
        if faces:
            panos.append({**{k: p[k] for k in ("id", "location_id", "position", "rotation")}, "faces": faces})
    withheld = sum(1 for v in scr.values() if not v.get("clear"))
    return {"building_id": bid, "mesh": idx["mesh"], "aerial": idx["aerial"], "panos": panos,
            "floors": idx["floors"], "rooms": idx["rooms"], "locations": idx["locations"],
            "screening": {"faces_total": 6 * len(idx["panos"]), "faces_screened": len(scr),
                          "faces_shown": shown, "faces_withheld": withheld,
                          "rule": "Panorama faces are shown only after a vision check finds no identifiable people, "
                                  "children's spaces or personal documents."},
            "notes": idx.get("notes", [])}


@app.get("/buildings/{bid}/media")
def building_media(bid: str):
    if bid == FIX:
        raise HTTPException(404, "the fixture building has no media")
    _real(bid)
    return manifest(bid)


@app.get("/media/{path:path}")
def media(path: str, request: Request):
    """Cached meshes, aerial images and screened panorama faces; `<id>/manifest.json` lists them. Localhost only."""
    if (request.client.host if request.client else "") not in LOCAL_HOSTS:
        raise HTTPException(403, "media is served to localhost only")
    m = re.match(r"^([a-z0-9-]+)/manifest\.json$", path)
    if m:
        _real(m.group(1))
        return manifest(m.group(1))
    f = FACE_PATH.match(path)
    if f and not _face_clear(f.group(1), f.group(2), int(f.group(3))):
        raise HTTPException(403, "panorama face not cleared by the privacy screen")
    root = MEDIA.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        if demo_mode() and target.is_relative_to(root):
            raise CacheMiss(f"DEMO_MODE=1: missing cached media {path}")
        raise HTTPException(404, "not found")
    return FileResponse(target)
