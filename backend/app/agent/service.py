"""Live agent sessions behind the API: one session per building, each turn on a background thread.

POST /run starts turn 1 (assess), POST /depth runs the re-plan turn, POST /send resumes the approval.
GET /events streams the live trace while a session runs, and replays the latest saved trace otherwise.
"""
import asyncio
import threading
from typing import AsyncIterator

from app.agent.replay import sse

_sessions: dict = {}
_threads: dict[str, threading.Thread] = {}
_errors: dict[str, str] = {}


class Busy(RuntimeError):
    pass


def _run(bid: str, fn) -> None:
    if bid in _threads and _threads[bid].is_alive():
        raise Busy(f"the agent is already working on {bid}")

    def target():
        try:
            _errors.pop(bid, None)
            fn()
        except Exception as e:                    # budget stop, model error: keep it visible in status
            _errors[bid] = f"{type(e).__name__}: {str(e)[:300]}"
    t = threading.Thread(target=target, daemon=True, name=f"agent-{bid}")
    _threads[bid] = t
    t.start()


def start(bid: str, depth_ft: float) -> dict:
    from app.agent.run import Session               # imported here: building the agent loads LangChain
    if bid in _threads and _threads[bid].is_alive():
        raise Busy(f"the agent is already working on {bid}")
    s = Session(bid, echo=False)
    _sessions[bid] = s
    _run(bid, lambda: s.assess(depth_ft))
    return status(bid)


def change_depth(bid: str, depth_ft: float, recipient: str) -> dict:
    s = _sessions.get(bid)
    if s is None:
        raise KeyError(bid)
    _run(bid, lambda: s.change_depth(depth_ft, recipient))
    return status(bid)


def request_send(bid: str, recipient: str) -> dict:
    s = _sessions.get(bid)
    if s is None:
        raise KeyError(bid)
    _run(bid, lambda: s.request_send(recipient))
    return status(bid)


def decide(bid: str, approve: bool, note: str = "") -> dict:
    s = _sessions.get(bid)
    if s is None or not waiting_for_approval(bid):
        raise KeyError(bid)
    _run(bid, lambda: s.decide(approve, note))
    return status(bid)


def running(bid: str) -> bool:
    return bid in _threads and _threads[bid].is_alive()


def waiting_for_approval(bid: str) -> bool:
    s = _sessions.get(bid)
    return bool(s and s.turns and s.turns[-1]["interrupted"] and not running(bid))


def memory_summary(bid: str, started_at: str | None) -> dict:
    """Active human corrections, and how many assets the agent applied them to in this session (agent-propagated
    corrections recorded since the session started; 0 without a session). Inactive corrections never count."""
    from datetime import datetime

    from app import corrections
    recs = corrections.load(bid)
    human = [r for r in recs if r["by"] == "human"]
    since = datetime.fromisoformat(started_at) if started_at else None
    applied = [r for r in recs if r["by"] != "human" and since and datetime.fromisoformat(r["ts"]) >= since]
    return {"active_human_corrections": len(human),
            "human_corrections": [{"id": r["id"], "asset_id": r["asset_id"], "action": r["action"],
                                   "changes": r.get("changes"), "note": r.get("note"), "at": r["ts"]} for r in human],
            "applied_this_session": len(applied),
            "applied_this_session_asset_ids": [r["asset_id"] for r in applied]}


def last_delivery(bid: str) -> dict | None:
    """The latest send attempt: status (sent, draft_only, refused, failed), recipient, time and detail."""
    from app.actions import send as send_action
    d = send_action.last(bid)
    return {"status": d["status"], "recipient": d["recipient"], "at": d["at"], "detail": d.get("detail")} if d else None


def status(bid: str) -> dict:
    s = _sessions.get(bid)
    extra = {"memory": memory_summary(bid, getattr(s, "started_at", None)), "last_delivery": last_delivery(bid)}
    if s is None:
        return {"building_id": bid, "session": None, **extra}
    return {"building_id": bid, "run_id": s.run_id, "running": running(bid), "turns": s.turns,
            "waiting_for_approval": waiting_for_approval(bid), "events": len(s.trace.events),
            "error": _errors.get(bid), "events_url": f"/buildings/{bid}/events", **extra}


def has_live(bid: str) -> bool:
    return bid in _sessions


def clear() -> None:
    """Forget every finished session (demo reset). Refuses while an agent is working."""
    busy = [b for b in _threads if running(b)]
    if busy:
        raise Busy(f"the agent is still working on {', '.join(busy)}")
    _sessions.clear()
    _threads.clear()
    _errors.clear()


async def live(bid: str, poll_s: float = 0.25, after: int = -1) -> AsyncIterator[str]:
    """Events of the current session after id `after` (all of them by default), then new ones as they arrive, until
    the turn ends."""
    s = _sessions[bid]
    sent = max(after + 1, 0)
    while True:
        evs = s.trace.events
        while sent < len(evs):
            yield sse("agent_event", evs[sent], evs[sent]["id"])
            sent += 1
        if not running(bid):
            break
        await asyncio.sleep(poll_s)
    yield sse("end", {"events": sent, "waiting_for_approval": waiting_for_approval(bid), "error": _errors.get(bid)})
