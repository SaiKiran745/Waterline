"""The Waterline deep agent (AGENTS.md section 10), built with deepagents 0.7.38.

Patterns follow ../hack-princeton-intro-to-deep-agents (agent.py, modules 01 and 02):
- planning: TodoListMiddleware adds write_todos (opt-in in current releases);
- subagents: six specs from subagents.py, delegated with the built-in task() tool;
- file system: CompositeBackend. The dossier (/dossier/<id>/...) lives in StateBackend (per thread, saved by the
  checkpointer). /memories/ routes to a StoreBackend on SQLite, so human corrections persist across runs and the API
  can write them (app/agent/memory.py);
- skills: /skills/survey/ and /skills/loss/ (SKILL.md files seeded into the thread's files on the first turn);
- human in the loop: interrupt_on={"send_playbook": ...}, with a SQLite checkpointer so the run can pause and resume.
The model is Gemini through langchain-google-genai, with GEMINI_API_KEY passed explicitly. Every model call (the
orchestrator, the subagents and the built-in general-purpose subagent share one model object) is priced into
data/cache/spend.json and refused before the budget would be passed.
"""
import os
import sqlite3
from functools import lru_cache
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend
from deepagents.backends.utils import create_file_data
from langchain.agents.middleware import ModelCallLimitMiddleware, TodoListMiddleware
from langchain_core.callbacks import BaseCallbackHandler
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.sqlite import SqliteSaver

from app.agent import memory, subagents
from app.agent.tools import ORCHESTRATOR_TOOLS
from app.config import CACHE, secret
from app.sources import spend

SKILLS_DIR = Path(__file__).parent / "skills"
CHECKPOINTS = CACHE / "agent" / "checkpoints.sqlite"

SYSTEM = """You are Waterline's orchestrator for building {bid}, a commercial building in Houston.
Goal: find where flood water gets in, inventory what a flood would damage, price the loss at the user's water depth,
rank the fixes, draft the report and pre-storm playbook, and get a person's approval before anything is sent.

How you work:
1. Memory first: call get_corrections for {bid}. Human corrections are your long-term memory. If it lists
   propagate_candidates, apply each with apply_correction_to_similar and give the reason.
2. Plan before acting: write a short plan (5 to 7 steps) with write_todos. Mark steps done as you go.
3. Delegate with task(), one subagent per call, giving the building id and the depth: site-scout, interior-surveyor,
   market-analyst, scenario-builder, mitigation-planner, communications. Do not do their work yourself.
4. Keep the dossier: write your decisions in a few lines to /dossier/{bid}/orchestrator.md.
5. Sending needs a person: when asked to send, call send_playbook; a person approves or rejects it.
6. When the user changes the depth: re-plan with write_todos (say what changes), have scenario-builder and
   mitigation-planner redo their work at the new depth, and say how the priority list changed and why.
Be brief. Every dollar figure is a low-high range; the depth is a scenario, not a forecast."""


class SpendCallback(BaseCallbackHandler):
    """Prices every chat-model call into spend.json and refuses a call that could pass the budget."""
    raise_error = True

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.calls = self.input_tokens = self.output_tokens = 0
        self.cost_usd = 0.0

    def on_chat_model_start(self, serialized, messages, **kw):
        spend.check("agent", self.model_name)

    def on_llm_start(self, serialized, prompts, **kw):
        spend.check("agent", self.model_name)

    def on_llm_end(self, response, **kw):
        for gens in response.generations:
            for g in gens:
                um = getattr(getattr(g, "message", None), "usage_metadata", None) or {}
                if not um:
                    continue
                inp = int(um.get("input_tokens") or 0)
                out = int((um.get("total_tokens") or 0) - inp) or int(um.get("output_tokens") or 0)
                self.cost_usd += spend.record("agent", self.model_name,
                                              {"promptTokenCount": inp, "candidatesTokenCount": out})
                self.calls += 1
                self.input_tokens += inp
                self.output_tokens += out


def model_name() -> str:
    spec = os.environ.get("AGENT_MODEL") or "google_genai:gemini-3.6-flash"
    provider, _, name = spec.partition(":")
    if provider != "google_genai":
        raise ValueError(f"AGENT_MODEL {spec}: only google_genai is wired")
    return name


def build_model(cb: SpendCallback) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=cb.model_name, google_api_key=secret("GEMINI_API_KEY"),
                                  thinking_config={"thinking_level": "LOW"}, max_retries=2, timeout=180,
                                  callbacks=[cb])


@lru_cache(maxsize=1)
def checkpointer() -> SqliteSaver:
    CHECKPOINTS.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(CHECKPOINTS, check_same_thread=False))


def build_agent(bid: str, cb: SpendCallback, model=None):
    """model: pass a test double to build the graph without calling Gemini."""
    m = model if model is not None else build_model(cb)
    backend = CompositeBackend(default=StateBackend(), routes={memory.ROUTE: memory.backend()})
    return create_deep_agent(
        model=m,
        tools=ORCHESTRATOR_TOOLS,
        system_prompt=SYSTEM.format(bid=bid),
        subagents=subagents.build(bid, []),
        middleware=[TodoListMiddleware(), ModelCallLimitMiddleware(run_limit=40, exit_behavior="end")],
        skills=["/skills/survey/", "/skills/loss/"],
        backend=backend,
        store=memory.store(),
        checkpointer=checkpointer(),
        interrupt_on={"send_playbook": {"allowed_decisions": ["approve", "reject"]}},
        name="waterline",
    )


def skill_files() -> dict:
    """SKILL.md files to seed into the thread's file system on the first turn (module 01 section 1.7 pattern)."""
    out = {}
    for f in SKILLS_DIR.rglob("SKILL.md"):
        out["/skills/" + str(f.relative_to(SKILLS_DIR))] = create_file_data(f.read_text())
    return out
