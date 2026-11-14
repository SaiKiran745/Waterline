"""Replay a saved AgentEvent trace as Server-Sent Events, paced by the events' own timestamps."""
import asyncio
import json
from datetime import datetime
from typing import AsyncIterator

MAX_GAP_S = 3.0   # long pauses in a trace (for example waiting for the user) are shortened to this


def _ts(e: dict) -> datetime:
    return datetime.fromisoformat(e["ts"].replace("Z", "+00:00"))


def sse(event: str, data, event_id=None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data)}\n\n"


def last_run(bid: str) -> dict | None:
    """The last saved agent run for a building: its trace and stats (data/cache/agent/traces|runs/<id>/)."""
    from app.agent.events import TRACES
    from app.config import CACHE, demo_mode
    if demo_mode():                                  # DEMO_MODE replays the pinned hero run (app/demo.py)
        from app import demo
        p = demo.pinned(bid)
        if p:
            run_id, events, stats = p
            recorded = events[0]["ts"] if events else None
            return {"building_id": bid, "run_id": run_id, "recorded_at": recorded, "events": len(events),
                    "seconds": stats.get("seconds"), "cost_usd": stats.get("cost_usd"),
                    "model_calls": stats.get("model_calls"), "turns": stats.get("turns"), "replay": True,
                    "label": f"REPLAY of a recorded live run ({run_id}, recorded {recorded}): not a live run",
                    "_events": events}
    tdir = TRACES / bid
    traces = sorted((p for p in tdir.glob("*.json") if p.name != "latest.json"), key=lambda p: p.stat().st_mtime) \
        if tdir.exists() else []
    if not traces:
        return None
    run_id = traces[-1].stem
    events = json.loads(traces[-1].read_text())
    stats_path = CACHE / "agent" / "runs" / bid / f"{run_id}.json"
    stats = json.loads(stats_path.read_text()) if stats_path.exists() else {}
    recorded = events[0]["ts"] if events else None
    return {"building_id": bid, "run_id": run_id, "recorded_at": recorded, "events": len(events),
            "seconds": stats.get("seconds"), "cost_usd": stats.get("cost_usd"), "model_calls": stats.get("model_calls"),
            "turns": stats.get("turns"), "replay": True,
            "label": f"REPLAY of the last saved run ({run_id}, recorded {recorded}): not a live run",
            "_events": events}


async def replay(events: list[dict], speed: float = 1.0, label: dict | None = None) -> AsyncIterator[str]:
    """speed=1 keeps the recorded pacing (gaps capped at MAX_GAP_S); speed=0 sends everything at once.
    label: sent first as a "replay" event (and repeated in "end") so the UI can say it is a replay."""
    if label:
        yield sse("replay", label)
    prev = None
    for e in events:
        if prev is not None and speed > 0:
            gap = min((_ts(e) - _ts(prev)).total_seconds(), MAX_GAP_S)
            await asyncio.sleep(max(gap, 0) / speed)
        yield sse("agent_event", e, e["id"])
        prev = e
    yield sse("end", {"events": len(events), "replay": bool(label), **({"label": label["label"]} if label else {})})
