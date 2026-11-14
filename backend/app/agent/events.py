"""AgentEvents (contracts/agent_event.schema.json): the live trace and its saved copy for replay.

Two sources feed one Trace:
- tools.py emits tool_call / observation / decision events itself, so every survey, re-look and ranking step is
  attributed to the right subagent without guessing from stream namespaces;
- translate() turns the deep agent's stream (stream_mode="updates", subgraphs=True) into plan / replan / decision /
  artifact / awaiting_approval events: write_todos, task() delegations, dossier files and the approval interrupt.
Every event is validated against the contract and appended to data/cache/agent/traces/<id>/<run_id>.json.
"""
import json
import threading
from datetime import datetime, timezone

from app.buildings import validate
from app.config import CACHE
from app.sources.cache import write_json

TRACES = CACHE / "agent" / "traces"
AGENTS = ("orchestrator", "site-scout", "interior-surveyor", "market-analyst", "scenario-builder",
          "mitigation-planner", "communications")
_lock = threading.Lock()
_current: "Trace | None" = None


def short(text: str, n: int = 400) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


class Trace:
    def __init__(self, building_id: str, run_id: str, echo: bool = False):
        self.building_id, self.run_id, self.echo = building_id, run_id, echo
        self.events: list[dict] = []
        self.path = TRACES / building_id / f"{run_id}.json"
        self.planned = False            # first write_todos is the plan
        self.replan_pending = False     # set when the depth changes: the next write_todos is a re-plan
        self.todos: list[str] = []
        self.delegated: list[str] = []  # subagents in the order they were given work (attribution of their files)
        self.task_ids: dict[str, str] = {}  # task() tool-call id -> subagent, so parallel reports are attributed right
        self.files: set[str] = set()
        self.skills: set[tuple[str, str]] = set()
        self.ns_role: dict[str, str] = {}               # subgraph namespace -> subagent, learned from its tool calls
        self.pending_skills: dict[str, list] = {}       # skill loads seen before the namespace's subagent is known
        self.listeners: list = []

    def emit(self, agent: str, type_: str, text: str, refs=(), data=None) -> dict:
        with _lock:
            ev = {"id": len(self.events), "building_id": self.building_id,
                  "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                  "agent": agent if agent in AGENTS else "orchestrator", "type": type_, "text": short(text, 600),
                  "refs": [str(r) for r in refs][:40], "data": data}
            validate("agent_event", ev)
            self.events.append(ev)
            write_json(self.path, self.events)
            write_json(self.path.parent / "latest.json", self.events)
        if self.echo:
            print(f"[{ev['id']:>3}] {ev['agent']:<18} {ev['type']:<17} {ev['text'][:160]}", flush=True)
        for fn in list(self.listeners):
            fn(ev)
        return ev


def activate(trace: "Trace | None") -> None:
    global _current
    _current = trace


def current() -> "Trace | None":
    return _current


def emit(agent: str, type_: str, text: str, refs=(), data=None) -> dict | None:
    return _current.emit(agent, type_, text, refs, data) if _current else None


def load_latest(building_id: str) -> list[dict]:
    p = TRACES / building_id / "latest.json"
    return json.loads(p.read_text()) if p.exists() else []


# ------------------------------------------------------------------ stream translation

def _msgs(update) -> list:
    if not isinstance(update, dict):
        return []
    m = update.get("messages")
    if m is None:
        return []
    if hasattr(m, "value"):          # Overwrite wrapper
        m = m.value
    return m if isinstance(m, list) else [m]


def _todo_texts(todos) -> list[str]:
    return [t.get("content", "") if isinstance(t, dict) else str(t) for t in todos or []]


def _skill_event(trace: Trace, who: str, skill: str, path: str) -> None:
    if (who, skill) not in trace.skills:
        trace.skills.add((who, skill))
        trace.emit(who, "tool_call", f"Loaded skill {skill} on demand ({path})", refs=[path],
                   data={"tool": "read_file", "skill": skill, "path": path})


def translate(trace: Trace, namespace: tuple, chunk: dict) -> None:
    """One (namespace, {node: update}) item from agent.stream(..., stream_mode="updates", subgraphs=True)."""
    in_subagent = bool(namespace)
    ns = "|".join(namespace) if namespace else ""
    who = trace.ns_role.get(ns) or (trace.delegated[-1] if in_subagent and trace.delegated else "orchestrator")
    if in_subagent and ns not in trace.ns_role:
        from app.agent.tools import ROLE_TOOLS
        owner = {t.name: role for role, ts in ROLE_TOOLS.items() for t in ts}
        for update in (chunk or {}).values():
            for m in _msgs(update):
                for call in getattr(m, "tool_calls", None) or []:
                    if call.get("name") in owner:
                        trace.ns_role[ns] = who = owner[call["name"]]
                        for skill, path in trace.pending_skills.pop(ns, []):
                            _skill_event(trace, who, skill, path)
    for node, update in (chunk or {}).items():
        if node == "__interrupt__":
            for intr in update or ():
                v = getattr(intr, "value", intr) or {}
                reqs = v.get("action_requests", []) if isinstance(v, dict) else []
                for r in reqs:
                    args = r.get("args") or r.get("arguments") or {}
                    trace.emit("communications", "awaiting_approval",
                               f"Waiting for a person to approve {r.get('name')}: send the pre-storm playbook to "
                               f"{args.get('recipient', '?')} at {args.get('depth_ft', '?')} ft. Nothing is sent "
                               "before Approve.", refs=[], data={"tool": r.get("name"), "args": args})
            continue
        for m in _msgs(update):
            mtype = getattr(m, "type", None)
            if mtype == "ai":
                for call in getattr(m, "tool_calls", None) or []:
                    name, args = call.get("name"), call.get("args") or {}
                    if name == "write_todos":
                        texts = _todo_texts(args.get("todos"))
                        if texts == trace.todos:
                            continue                         # status-only update: not a new plan
                        kind = "replan" if trace.replan_pending else "plan"
                        if trace.planned and not trace.replan_pending:
                            kind = "plan"
                        trace.emit(who, kind, ("Re-plan: " if kind == "replan" else "Plan: ") + "; ".join(texts),
                                   data={"steps": texts, "statuses": [t.get("status") for t in args.get("todos") or []
                                                                      if isinstance(t, dict)]})
                        trace.todos, trace.planned = texts, True
                        if kind == "replan":
                            trace.replan_pending = False
                    elif name == "task":
                        sub = args.get("subagent_type") or args.get("name") or "general-purpose"
                        trace.delegated.append(sub)
                        if call.get("id"):
                            trace.task_ids[call["id"]] = sub
                        trace.emit("orchestrator", "decision", f"Delegate to {sub}: {args.get('description', '')}",
                                   data={"tool": "task", "subagent": sub})
                    elif name == "read_file" and "/skills/" in str(args.get("file_path") or args.get("path") or ""):
                        path = str(args.get("file_path") or args.get("path"))
                        skill = path.rstrip("/").split("/")[-2] if path.endswith("SKILL.md") else path
                        if in_subagent and ns not in trace.ns_role:
                            trace.pending_skills.setdefault(ns, []).append((skill, path))   # owner not known yet
                        else:
                            _skill_event(trace, who, skill, path)
                    elif name in ("write_file", "edit_file"):
                        path = args.get("file_path") or args.get("path") or ""
                        if path.startswith("/dossier/") or path.startswith("/memories/"):
                            stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                            trace.emit(stem if stem in AGENTS else who, "artifact", f"{'Wrote' if name == 'write_file' else 'Updated'} {path}",
                                       refs=[path], data={"tool": name, "path": path})
                text = getattr(m, "text", None)
                text = text() if callable(text) else text
                if text and not getattr(m, "tool_calls", None) and not in_subagent:
                    trace.emit("orchestrator", "decision", text)
            elif mtype == "tool" and getattr(m, "name", "") == "task" and not in_subagent:
                body = getattr(m, "content", "")
                body = body if isinstance(body, str) else json.dumps(body)[:2000]
                sub = trace.task_ids.get(getattr(m, "tool_call_id", None) or "") or \
                    (trace.delegated[-1] if trace.delegated else "orchestrator")
                trace.emit(sub, "observation", f"Reported back: {body}")
