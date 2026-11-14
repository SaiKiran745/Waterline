"""Run the Waterline agent on a building: a three-turn session on one thread, traced as AgentEvents.

    python -m app.agent.run building-e --depth 1 --new-depth 4 --approve [--quick-scan 12]

Turn 1 (assess): memory, plan, site, interior survey (every scan position, in batches of whole areas, largest first;
--quick-scan N is an optional position budget, off by default), value, scenario, fixes at --depth.
Turn 2 (replan): the user moves the slider to --new-depth: re-plan, re-price, re-rank only.
Turn 3 (send): draft the report and playbook, then send_playbook, which pauses for a person.
Turn 4 (approval): a person approves (or rejects) the send.
The trace is saved to data/cache/agent/traces/<id>/<run_id>.json (and latest.json, which GET /events replays);
run stats (model calls, tokens, cost, time) to data/cache/agent/runs/<id>/<run_id>.json.
"""
import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone

from langgraph.types import Command

from app.agent import events, orchestrator, tools
from app.config import CACHE
from app.sources import spend
from app.sources.cache import write_json

RUNS = CACHE / "agent" / "runs"


class Session:
    def __init__(self, bid: str, echo: bool = True, cached_positions_only: bool = False, quick_scan: int | None = None):
        self.bid = bid
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
        self.trace = events.Trace(bid, self.run_id, echo=echo)
        self.cb = orchestrator.SpendCallback(orchestrator.model_name())
        self.sub_cb = orchestrator.SpendCallback(orchestrator.subagent_model_name())
        tools.reset(bid)
        old = tools.DOSSIER / bid                      # each session starts a clean dossier; the send log is an audit trail
        if old.exists():
            for f in old.rglob("*"):
                if f.is_file() and f.name != "sends.json":
                    f.unlink()
        tools.SETTINGS.update(cached_positions_only=cached_positions_only, quick_scan=quick_scan)
        self.agent = orchestrator.build_agent(bid, self.cb, sub_cb=self.sub_cb)
        self.config = {"configurable": {"thread_id": f"{bid}-{self.run_id}"}, "recursion_limit": 300}
        self.spend_start = spend.summary()["total_usd"]
        self.t0 = time.time()
        self.turns: list[dict] = []
        self.depth = None

    def _stream(self, inp, label: str) -> dict:
        events.activate(self.trace)
        t = time.time()
        calls0, cost0 = self.calls(), self.cost()
        interrupted = False
        try:
            for ns, chunk in self.agent.stream(inp, self.config, stream_mode="updates", subgraphs=True):
                if isinstance(chunk, dict) and "__interrupt__" in chunk and not ns:
                    interrupted = True
                events.translate(self.trace, ns, chunk)
        finally:
            events.activate(None)
        self._save_dossier()
        turn = {"turn": label, "seconds": round(time.time() - t, 1), "model_calls": self.calls() - calls0,
                "cost_usd": round(self.cost() - cost0, 4), "interrupted": interrupted}
        self.turns.append(turn)
        self._save_stats()
        return turn

    def calls(self) -> int:
        return self.cb.calls + self.sub_cb.calls

    def cost(self) -> float:
        return self.cb.cost_usd + self.sub_cb.cost_usd

    def _save_dossier(self) -> None:
        state = self.agent.get_state(self.config)
        files = (state.values or {}).get("files") or {}
        out = tools.DOSSIER / self.bid
        for path, fd in files.items():
            if not path.startswith(f"/dossier/{self.bid}/"):
                continue
            content = fd.get("content") if isinstance(fd, dict) else fd
            content = "\n".join(content) if isinstance(content, list) else str(content)
            dest = out / path.split(f"/dossier/{self.bid}/", 1)[1]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)

    def _save_stats(self) -> None:
        write_json(RUNS / self.bid / f"{self.run_id}.json", {
            "building_id": self.bid, "run_id": self.run_id, "model": self.cb.model_name,
            "subagent_model": self.sub_cb.model_name, "turns": self.turns, "model_calls": self.calls(),
            "by_model": {c.model_name if c is self.cb else f"{c.model_name} (subagents)":
                         {"calls": c.calls, "input_tokens": c.input_tokens, "output_tokens": c.output_tokens,
                          "cost_usd": round(c.cost_usd, 4)} for c in (self.cb, self.sub_cb)},
            "input_tokens": self.cb.input_tokens + self.sub_cb.input_tokens,
            "output_tokens": self.cb.output_tokens + self.sub_cb.output_tokens,
            "cost_usd": round(self.cost(), 4), "seconds": round(time.time() - self.t0, 1),
            "events": len(self.trace.events), "trace": str(self.trace.path.relative_to(CACHE)),
            "spend_total_usd": spend.summary()["total_usd"]})

    def assess(self, depth: float) -> dict:
        self.depth = depth
        q = tools.SETTINGS["quick_scan"]
        survey = ("the surveyor reads every scan position, in batches, largest areas first" if q is None else
                  f"QUICK SCAN: the surveyor reads {q} scan positions split across areas by size")
        msg = (f"Assess {self.bid} for {depth:g} ft of interior water: site, interior ({survey}), value, loss and "
               f"ranked fixes at {depth:g} ft. Do not draft or send documents yet.")
        return self._stream({"messages": [{"role": "user", "content": msg}], "files": orchestrator.skill_files()},
                            "assess")

    def change_depth(self, new_depth: float, recipient: str) -> dict:
        old, self.depth = self.depth, new_depth
        self.trace.replan_pending = True
        self.trace.emit("orchestrator", "observation", f"The user moved the depth slider from {old:g} ft to {new_depth:g} ft.",
                        data={"from_ft": old, "to_ft": new_depth})
        msg = (f"The user moved the depth slider from {old:g} ft to {new_depth:g} ft. Re-plan, re-price and re-rank at "
               f"{new_depth:g} ft and say how the priority list changed.")
        return self._stream({"messages": [{"role": "user", "content": msg}]}, "replan")

    def request_send(self, recipient: str) -> dict:
        msg = (f"Draft the report and playbook at {self.depth:g} ft, then call send_playbook(building_id='{self.bid}', "
               f"recipient='{recipient}', depth_ft={self.depth:g}).")
        return self._stream({"messages": [{"role": "user", "content": msg}]}, "send")

    def decide(self, approve: bool, note: str = "") -> dict:
        self.trace.emit("orchestrator", "decision",
                        f"A person {'approved' if approve else 'rejected'} the send." + (f" {note}" if note else ""),
                        data={"approved": approve})
        decision = {"type": "approve"} if approve else {"type": "reject", "message": note or "Not now."}
        return self._stream(Command(resume={"decisions": [decision]}), "approval")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("building")
    ap.add_argument("--depth", type=float, default=1.0)
    ap.add_argument("--new-depth", type=float, default=4.0)
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--quick-scan", type=int, default=None, metavar="N",
                    help="optional quick scan: read only N scan positions, split across areas by size (off by default)")
    ap.add_argument("--cached-only", action="store_true", help="offer only positions with cached vision answers")
    a = ap.parse_args()
    recipient = next((r.strip() for r in os.environ.get("ALLOWED_RECIPIENTS", "").split(",") if r.strip()), "")
    s = Session(a.building, cached_positions_only=a.cached_only, quick_scan=a.quick_scan)
    print(f"run {s.run_id}: model {s.cb.model_name}; spend before ${s.spend_start:.4f}", flush=True)
    for step in (lambda: s.assess(a.depth), lambda: s.change_depth(a.new_depth, recipient),
                 lambda: s.request_send(recipient),
                 lambda: s.decide(a.approve, "" if a.approve else "Rejected from the command line.")):
        turn = step()
        print(f"--- turn {turn}", flush=True)
        if turn["turn"] == "send" and not turn["interrupted"]:
            print("no approval interrupt reached; stopping before the approval turn", flush=True)
            break
    st = json.loads((RUNS / s.bid / f"{s.run_id}.json").read_text())
    print(json.dumps({k: st[k] for k in ("model_calls", "input_tokens", "output_tokens", "cost_usd", "seconds",
                                         "events", "spend_total_usd")}))


if __name__ == "__main__":
    main()
