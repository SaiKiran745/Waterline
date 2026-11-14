"""Waterline API (AGENTS.md section 8; contracts/ v1.1.0).

Real buildings come from data/cache/ (built by `python -m app.sources.pull`); ids are slugs ("building-a").
`fixture-1` is the FIXTURE building from contracts/fixtures/ and supports every endpoint.

Run: uvicorn app.main:app --host 127.0.0.1 --port 8000
"""
import json
import mimetypes
import os
import re

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from app import buildings, corrections, fixtures
from app.actions import playbook as playbook_html
from app.actions import report as report_html
from app.agent.replay import replay
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
    """Buildings ranked by precomputed total loss (high end) at 2 ft, then by letter. ?fixture=1 for FIXTURE data."""
    if fixture:
        return [fixtures.building()]
    r = rank.load()
    return sorted(buildings.list_buildings(), key=lambda b: (-(r.get(b["id"], {}).get("2", {}).get("total", [0, 0])[1]), b["id"]))


@app.get("/triage")
def triage(depth_ft: int = Query(2), fixture: int = 0):
    """Triage ranking (not in contracts/ yet): every building ranked by total loss at 1, 2 or 4 ft, each labelled
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


@app.post("/buildings/{bid}/run")
def run(bid: str, body: dict | None = Body(default=None)):
    if bid == FIX:
        return {"status": "replay", "building_id": bid, "depth_ft": (body or {}).get("depth_ft"),
                "events_url": f"/buildings/{bid}/events", "note": "FIXTURE trace replay; the live agent arrives in Phase 5"}
    _real(bid)
    raise HTTPException(501, f"The live agent arrives in Phase 5; use {FIX} until then")


@app.get("/buildings/{bid}/events")
def events(bid: str, speed: float = Query(1.0, ge=0, le=100)):
    if bid != FIX:
        _real(bid)
        raise HTTPException(501, f"Agent events arrive in Phase 5; use {FIX} until then")
    return StreamingResponse(replay(fixtures.load("agent_events.json"), speed), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/buildings/{bid}/report", response_class=HTMLResponse)
def report(bid: str, depth_ft: float = Query(2, ge=0, le=8)):
    if bid == FIX:
        return fixtures.report_html()
    return report_html.render(_real(bid), buildings.get_assets(bid), buildings.get_entry_points(bid), depth_ft)


@app.get("/buildings/{bid}/playbook", response_class=HTMLResponse)
def playbook(bid: str, depth_ft: float = Query(2, ge=0, le=8)):
    if bid == FIX:
        return fixtures.playbook_html()
    return playbook_html.render(_real(bid), buildings.get_assets(bid), buildings.get_entry_points(bid), depth_ft)


@app.post("/buildings/{bid}/send")
def send(bid: str, body: dict = Body(...)):
    """Requires {"approved": true, "recipient": "<address in ALLOWED_RECIPIENTS>"}. Nothing is sent before Phase 5B."""
    if bid != FIX:
        _real(bid)
    if body.get("approved") is not True:
        raise HTTPException(400, 'sending requires {"approved": true}')
    allowed = {a.strip().lower() for a in os.environ.get("ALLOWED_RECIPIENTS", "").split(",") if a.strip()}
    recipient = str(body.get("recipient", "")).strip().lower()
    if recipient not in allowed:
        raise HTTPException(403, "recipient is not in ALLOWED_RECIPIENTS")
    return {"status": "not_sent", "building_id": bid, "recipient": recipient,
            "reason": "Sending is built in Phase 5B. Approval was recorded; nothing was sent."}


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
