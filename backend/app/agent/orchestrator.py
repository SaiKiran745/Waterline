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
Goal: where flood water gets in, what a flood would damage, the loss at the user's depth, the fixes ranked, the
documents drafted, and a person's approval before anything is sent.

Rules:
1. Plan before acting: write_todos with 4 to 6 short steps, one of them "apply human corrections".
2. Memory: once the interior survey is done (before pricing), call get_corrections. For each correction with
   candidates in apply_to_similar, judge every candidate against the person's note: apply it only where the note
   clearly describes that asset too. Call apply_correction_to_similar once per correction with the assets you chose
   (possibly none) and a reason that names any you skipped and why.
3. Delegate with task(), one subagent per call, building id and depth in the description. Run independent work in
   parallel: site-scout, interior-surveyor and market-analyst together; then scenario-builder and mitigation-planner
   together. Do not do their work yourself. Their replies are exact tool results; quote numbers from them only.
4. Details live in /dossier/{bid}/ (the tools write them). Keep your messages short; never paste tables.
5. When the user changes the depth: re-plan with write_todos, then only scenario-builder and mitigation-planner at
   the new depth (tell the planner the old depth). Say in 3 lines how the priority list changed.
6. Sending needs a person: when asked to send, have communications draft first (no new plan needed), then you must
   call send_playbook (never just ask in text). It pauses until a person approves or rejects it.
Every dollar figure is a median with its 80% interval, quoted from a tool result; the depth is a scenario, not a
forecast. Final answers: at most 5 lines."""


# The default write_todos texts are about 2,000 tokens and ride on every orchestrator call; these say the same for us.
PLAN_PROMPT = ("## write_todos\nWrite the plan with write_todos before acting (4 to 6 short steps) and again only "
               "when the plan itself changes. Do not call it just to mark steps done.")
PLAN_TOOL = ("Write or replace the plan: a list of todos, each with content and a status (pending, in_progress or "
             "completed).")


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


def model_name(var: str = "AGENT_MODEL", default: str = "google_genai:gemini-3.6-flash") -> str:
    spec = os.environ.get(var) or default
    provider, _, name = spec.partition(":")
    if provider != "google_genai":
        raise ValueError(f"{var} {spec}: only google_genai is wired")
    return name


def subagent_model_name() -> str:
    return model_name("AGENT_SUBAGENT_MODEL", os.environ.get("AGENT_MODEL") or "google_genai:gemini-3.6-flash")


def build_model(cb: SpendCallback) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=cb.model_name, google_api_key=secret("GEMINI_API_KEY"),
                                  thinking_config={"thinking_level": "LOW"}, max_retries=2, timeout=180,
                                  callbacks=[cb])


@lru_cache(maxsize=1)
def checkpointer() -> SqliteSaver:
    CHECKPOINTS.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(CHECKPOINTS, check_same_thread=False))


def build_agent(bid: str, cb: SpendCallback, model=None, sub_cb: SpendCallback | None = None):
    """model: pass a test double to build the graph without calling Gemini (subagents then use it too)."""
    m = model if model is not None else build_model(cb)
    sub = model if model is not None else (build_model(sub_cb) if sub_cb else None)
    backend = CompositeBackend(default=StateBackend(), routes={memory.ROUTE: memory.backend()})
    return create_deep_agent(
        model=m,
        tools=ORCHESTRATOR_TOOLS,
        system_prompt=SYSTEM.format(bid=bid),
        subagents=subagents.build(bid, sub),
        middleware=[TodoListMiddleware(system_prompt=PLAN_PROMPT, tool_description=PLAN_TOOL),
                    ModelCallLimitMiddleware(run_limit=40, exit_behavior="end")],
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
