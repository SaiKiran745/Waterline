"""Waterline API (AGENTS.md section 8).

Real buildings come from data/cache/ (built by `python -m app.sources.pull`).
`fixture-1` is the FIXTURE building from contracts/fixtures/ and supports every endpoint.
For real buildings, assets and entry points are empty until Phases 3-4, and the scenario, mitigation,
agent and report endpoints answer 501 until those phases exist.

Run: uvicorn app.main:app --host 127.0.0.1 --port 8000
"""
import mimetypes
import os

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from app import buildings, fixtures
from app.agent.replay import replay
from app.config import FRONTEND_ORIGINS, MEDIA, demo_mode
from app.sources.cache import CacheMiss

app = FastAPI(title="Waterline API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"])

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
FIX = fixtures.FIXTURE_ID
mimetypes.add_type("text/plain", ".obj")


@app.exception_handler(CacheMiss)
async def cache_miss(_: Request, exc: CacheMiss):
    return JSONResponse(status_code=503, content={"detail": str(exc), "demo_mode": demo_mode()})


def _real_or_404(bid: str) -> None:
    if bid not in buildings.building_ids():
        raise HTTPException(404, f"unknown building {bid}")


def _not_yet(bid: str, what: str, phase: str):
    _real_or_404(bid)
    raise HTTPException(501, f"{what} for real buildings arrives in {phase}; use {FIX} until then")


@app.get("/health")
def health():
    return {"ok": True, "demo_mode": demo_mode()}


@app.get("/buildings")
def list_buildings(fixture: int = 0):
    """Shortlisted buildings in letter order (ranking by loss arrives with the loss model). ?fixture=1 for FIXTURE data."""
    if fixture:
        return [fixtures.building()]
    return buildings.list_buildings()


@app.get("/buildings/{bid}")
def get_building(bid: str):
    if bid == FIX:
        return fixtures.detail()
    _real_or_404(bid)
    return {"building": buildings.get_building(bid), "entry_points": [], "assets": []}


@app.get("/buildings/{bid}/scenario")
def scenario(bid: str, depth_ft: float = Query(..., ge=0, le=8)):
    if bid == FIX:
        return fixtures.scenario(depth_ft)
    _not_yet(bid, "Scenarios", "Phase 4")


@app.get("/buildings/{bid}/mitigations")
def mitigations(bid: str, depth_ft: float = Query(2, ge=0, le=8)):
    if bid == FIX:
        return fixtures.mitigations(depth_ft)
    _not_yet(bid, "Mitigations", "Phase 4")


@app.post("/buildings/{bid}/run")
def run(bid: str, body: dict | None = Body(default=None)):
    if bid == FIX:
        return {"status": "replay", "building_id": bid, "depth_ft": (body or {}).get("depth_ft"),
                "events_url": f"/buildings/{bid}/events", "note": "FIXTURE trace replay; the live agent arrives in Phase 5"}
    _not_yet(bid, "The agent", "Phase 5")


@app.get("/buildings/{bid}/events")
def events(bid: str, speed: float = Query(1.0, ge=0, le=100)):
    if bid != FIX:
        _not_yet(bid, "Agent events", "Phase 5")
    return StreamingResponse(replay(fixtures.load("agent_events.json"), speed), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/buildings/{bid}/report", response_class=HTMLResponse)
def report(bid: str):
    if bid == FIX:
        return fixtures.report_html()
    _not_yet(bid, "Reports", "Phase 5")


@app.get("/buildings/{bid}/playbook", response_class=HTMLResponse)
def playbook(bid: str):
    if bid == FIX:
        return fixtures.playbook_html()
    _not_yet(bid, "Playbooks", "Phase 5")


@app.post("/buildings/{bid}/send")
def send(bid: str, body: dict = Body(...)):
    """Requires {"approved": true, "recipient": "<address in ALLOWED_RECIPIENTS>"}. Nothing is sent before Phase 5B."""
    if bid != FIX:
        _real_or_404(bid)
    if body.get("approved") is not True:
        raise HTTPException(400, 'sending requires {"approved": true}')
    allowed = {a.strip().lower() for a in os.environ.get("ALLOWED_RECIPIENTS", "").split(",") if a.strip()}
    recipient = str(body.get("recipient", "")).strip().lower()
    if recipient not in allowed:
        raise HTTPException(403, "recipient is not in ALLOWED_RECIPIENTS")
    return {"status": "not_sent", "building_id": bid, "recipient": recipient,
            "reason": "Sending is built in Phase 5B. Approval was recorded; nothing was sent."}


@app.get("/media/{path:path}")
def media(path: str, request: Request):
    """Cached meshes, panoramas, aerial images and per-building manifest.json. Local requests only."""
    if (request.client.host if request.client else "") not in LOCAL_HOSTS:
        raise HTTPException(403, "media is served to localhost only")
    root = MEDIA.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        if demo_mode() and target.is_relative_to(root):
            raise CacheMiss(f"DEMO_MODE=1: missing cached media {path}")
        raise HTTPException(404, "not found")
    return FileResponse(target)
