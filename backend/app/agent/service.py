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


def start(bid: str, depth_ft: float, quick_scan: int | None = None) -> dict:
    from app.agent.run import Session               # imported here: building the agent loads LangChain
    if bid in _threads and _threads[bid].is_alive():
        raise Busy(f"the agent is already working on {bid}")
    s = Session(bid, echo=False, quick_scan=quick_scan)
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


def status(bid: str) -> dict:
    s = _sessions.get(bid)
    if s is None:
        return {"building_id": bid, "session": None}
    return {"building_id": bid, "run_id": s.run_id, "running": running(bid), "turns": s.turns,
            "waiting_for_approval": waiting_for_approval(bid), "events": len(s.trace.events),
            "error": _errors.get(bid), "events_url": f"/buildings/{bid}/events"}


def has_live(bid: str) -> bool:
    return bid in _sessions


async def live(bid: str, poll_s: float = 0.25) -> AsyncIterator[str]:
    """Every event of the current session so far, then new ones as they arrive, until the turn ends."""
    s = _sessions[bid]
    sent = 0
    while True:
        evs = s.trace.events
        while sent < len(evs):
            yield sse("agent_event", evs[sent], evs[sent]["id"])
            sent += 1
        if not running(bid):
            break
        await asyncio.sleep(poll_s)
    yield sse("end", {"events": sent, "waiting_for_approval": waiting_for_approval(bid), "error": _errors.get(bid)})
