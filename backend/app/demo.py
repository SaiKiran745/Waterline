"""Demo readiness: a known starting state, and the pinned hero run that DEMO_MODE replays.

    python -m app.demo snapshot            # record the current stored surveys and corrections as the baseline
    python -m app.demo reset               # restore it (also POST /demo/reset, which also clears agent sessions)
    python -m app.demo pin building-e      # pin the latest saved run (and its resulting corrections) as the replay
    python -m app.demo status

The starting state: every building's full stored survey (positions read as in the baseline), exactly one human
correction on E and no agent copies of it, no agent session, an empty dossier (the send log is kept), and depth 1 ft.
Reset reads and writes only data/cache/; it makes no model or network calls and is safe to run repeatedly.
Everything lives under data/cache/demo/ (git-ignored).
"""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone

from app import buildings, corrections
from app.config import BUILDINGS, CACHE
from app.sources.cache import write_json

ROOT = CACHE / "demo"
BASELINE = ROOT / "baseline"
PINNED = ROOT / "replay"
STATE = ROOT / "state.json"
FILES = ("assets.json", "asset_geometry.json", "survey_log.json", "screening.json", "corrections.json")
START_DEPTH_FT = 1.0
HUMAN_CORRECTIONS = {"building-e": 1}            # exactly one on E, none elsewhere


class DemoError(RuntimeError):
    pass


def _sha(p) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def _read(bid: str) -> dict:
    log = json.loads((BUILDINGS / bid / "survey_log.json").read_text())
    mp = json.loads((BUILDINGS / bid / "parts.json").read_text())["matterport"]
    recs = corrections.load(bid)
    return {"positions_read": sum(1 for p in log["positions"] if not p.get("error")), "scan_positions": len(mp["panos"]),
            "assets": len(buildings.get_survey_assets(bid)),
            "human_corrections": sum(1 for r in recs if r["by"] == "human"),
            "agent_corrections": sum(1 for r in recs if r["by"] != "human")}


def snapshot() -> dict:
    """Record the baseline from the current cache. Agent copies of corrections are left out: the hero run makes them."""
    manifest = {"taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "buildings": {}}
    for bid in sorted(buildings.building_ids()):
        human = [r for r in corrections.load(bid) if r["by"] == "human"]
        if len(human) != HUMAN_CORRECTIONS.get(bid, 0):
            raise DemoError(f"{bid} has {len(human)} human corrections; the demo needs {HUMAN_CORRECTIONS.get(bid, 0)}")
        dest = BASELINE / bid
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        for f in FILES:
            src = BUILDINGS / bid / f
            if f == "corrections.json":
                if human:
                    write_json(dest / f, human)
            elif src.exists():
                shutil.copy2(src, dest / f)
        st = _read(bid)
        st.update(agent_corrections=0, files={f: _sha(dest / f) for f in FILES if (dest / f).exists()})
        manifest["buildings"][bid] = st
    write_json(BASELINE / "manifest.json", manifest)
    return manifest


def reset() -> dict:
    """Restore the baseline: stored surveys, corrections and memory; clear dossiers; recompute the triage ranking."""
    if not (BASELINE / "manifest.json").exists():
        raise DemoError("no demo baseline: run `python -m app.demo snapshot` once")
    from app.agent import memory
    from app.loss import rank
    manifest = json.loads((BASELINE / "manifest.json").read_text())
    out = {}
    for bid, want in manifest["buildings"].items():
        src, dst = BASELINE / bid, BUILDINGS / bid
        for f in FILES:
            if (src / f).exists():
                shutil.copy2(src / f, dst / f)
            elif (dst / f).exists():
                (dst / f).unlink()               # e.g. corrections made after the snapshot
        memory.rewrite(bid, corrections.load(bid))
        dossier = CACHE / "agent" / "dossier" / bid
        if dossier.exists():
            for f in dossier.rglob("*"):
                if f.is_file() and f.name != "sends.json":
                    f.unlink()
        got = _read(bid)
        for k in ("positions_read", "scan_positions", "assets", "human_corrections", "agent_corrections"):
            if got[k] != want[k]:
                raise DemoError(f"{bid}: {k} is {got[k]} after reset, baseline says {want[k]}")
        out[bid] = got
    rank.compute()
    state = {"reset_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "depth_ft": START_DEPTH_FT,
             "agent_session": None, "baseline_taken_at": manifest["taken_at"], "buildings": out}
    write_json(STATE, state)
    return state


def state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"depth_ft": START_DEPTH_FT, "reset_at": None}


def pin(bid: str, run_id: str | None = None) -> dict:
    """Make a saved run the replay DEMO_MODE serves for this building."""
    from app.agent.events import TRACES
    traces = sorted((p for p in (TRACES / bid).glob("*.json") if p.name != "latest.json"), key=lambda p: p.stat().st_mtime)
    path = (TRACES / bid / f"{run_id}.json") if run_id else (traces[-1] if traces else None)
    if path is None or not path.exists():
        raise DemoError(f"no saved run {run_id or ''} for {bid}")
    stats = CACHE / "agent" / "runs" / bid / f"{path.stem}.json"
    dest = PINNED / bid
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest / "trace.json")
    if stats.exists():
        shutil.copy2(stats, dest / "stats.json")
    after = BUILDINGS / bid / "corrections.json"      # the run's outcome: the human correction plus the agent's copies
    if after.exists():
        shutil.copy2(after, dest / "corrections_after.json")
    write_json(dest / "pinned.json", {"run_id": path.stem, "pinned_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return {"building_id": bid, "run_id": path.stem, "events": len(json.loads(path.read_text()))}


def apply_replay_outcome(bid: str) -> bool:
    """DEMO_MODE replay: put the pinned run's resulting corrections in place, so the numbers the UI fetches match the
    ones the replayed trace quotes. A reset puts the starting state back."""
    src = PINNED / bid / "corrections_after.json"
    if not src.exists():
        return False
    from app.agent import memory
    from app.loss import rank
    shutil.copy2(src, BUILDINGS / bid / "corrections.json")
    memory.rewrite(bid, corrections.load(bid))
    rank.compute()
    return True


def pinned(bid: str) -> tuple[str, list[dict], dict] | None:
    d = PINNED / bid
    if not (d / "pinned.json").exists():
        return None
    run_id = json.loads((d / "pinned.json").read_text())["run_id"]
    stats = json.loads((d / "stats.json").read_text()) if (d / "stats.json").exists() else {}
    return run_id, json.loads((d / "trace.json").read_text()), stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["snapshot", "reset", "pin", "status"])
    ap.add_argument("building", nargs="?")
    ap.add_argument("run_id", nargs="?")
    a = ap.parse_args()
    if a.action == "snapshot":
        r = snapshot()
    elif a.action == "reset":
        r = reset()
    elif a.action == "pin":
        r = pin(a.building or "building-e", a.run_id)
    else:
        r = {"state": state(), "pinned": {b: (pinned(b) or (None,))[0] for b in sorted(buildings.building_ids())}}
    print(json.dumps(r, indent=1))
