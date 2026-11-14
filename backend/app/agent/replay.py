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


async def replay(events: list[dict], speed: float = 1.0) -> AsyncIterator[str]:
    """speed=1 keeps the recorded pacing (gaps capped at MAX_GAP_S); speed=0 sends everything at once."""
    prev = None
    for e in events:
        if prev is not None and speed > 0:
            gap = min((_ts(e) - _ts(prev)).total_seconds(), MAX_GAP_S)
            await asyncio.sleep(max(gap, 0) / speed)
        yield sse("agent_event", e, e["id"])
        prev = e
    yield sse("end", {"events": len(events)})
