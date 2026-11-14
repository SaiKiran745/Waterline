"""The agent's long-term memory: /memories/ in the deep agent's file system, kept in SQLite across runs.

Pattern from hack-princeton-intro-to-deep-agents module 01 section 1.4: CompositeBackend(default=StateBackend(),
routes={"/memories/": StoreBackend(store=SqliteStore, namespace=...)}). The namespace factory ignores the runtime,
so the API can write here outside a graph run (StoreBackend passes runtime=None when there is no graph).

CompositeBackend strips the route prefix, so the agent's "/memories/corrections/<id>.md" is the store key
"/corrections/<id>.md". Human corrections land there the moment the API saves them; the agent reads them at the
start of every run (system prompt) and applies them to similar assets (AGENTS.md section 10, behaviour 6).
"""
import sqlite3
from functools import lru_cache

from deepagents.backends import StoreBackend
from langgraph.store.sqlite import SqliteStore

from app.config import CACHE

MEMORY_DB = CACHE / "agent" / "memory.sqlite"
NAMESPACE = ("waterline", "memories")
ROUTE = "/memories/"


@lru_cache(maxsize=1)
def store() -> SqliteStore:
    MEMORY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(MEMORY_DB, check_same_thread=False, isolation_level=None)
    s = SqliteStore(conn)
    s.setup()
    return s


def backend() -> StoreBackend:
    return StoreBackend(store=store(), namespace=lambda _rt: NAMESPACE)


def _key(bid: str) -> str:
    return f"/corrections/{bid}.md"


def agent_path(bid: str) -> str:
    """Where the agent sees a building's corrections."""
    return ROUTE + _key(bid).lstrip("/")


def read_corrections(bid: str) -> str:
    item = store().get(NAMESPACE, _key(bid))
    if item is None:
        return ""
    c = item.value.get("content")
    return "\n".join(c) if isinstance(c, list) else str(c or "")


def record_correction(rec: dict, asset: dict) -> None:
    """Append one human (or propagated) correction as a line the agent can act on."""
    existing = read_corrections(rec["building_id"])
    if not existing:
        existing = (f"# Corrections for {rec['building_id']}\n\n"
                    "Each line is a correction a person made (or the agent propagated). Apply the same correction to "
                    "similar assets in this building, then re-run the scenario and the mitigation ranking.\n")
    if rec["action"] == "delete":
        what = f"DELETED {asset['id']} '{asset['label']}' ({asset['category']}, room {asset['room']})"
    else:
        what = (f"CHANGED {asset['id']} '{asset['label']}' ({asset['category']}, room {asset['room']}): "
                + "; ".join(f"{k} {rec['before'].get(k)!r} -> {v!r}" for k, v in rec["changes"].items()))
    who = "human" if rec["by"] == "human" else f"agent, propagating {rec['propagated_from']}"
    line = f"- {rec['ts'][:19]}Z [{rec['id']}] by {who}: {what}" + (f". Reason: {rec['note']}" if rec.get("note") else "")
    backend().write(_key(rec["building_id"]), existing.rstrip("\n") + "\n" + line + "\n")
