"""Agent wiring without model calls: graph builds, approval interrupt and resume, trace translation, tools."""
import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app import buildings
from app.agent import events, memory, orchestrator, tools

BID = "building-e"
pytestmark = pytest.mark.skipif(BID not in buildings.building_ids(), reason="building-e not pulled")


class FakeToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kw):
        return self


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator, "CHECKPOINTS", tmp_path / "ck.sqlite")
    orchestrator.checkpointer.cache_clear()
    monkeypatch.setattr(memory, "MEMORY_DB", tmp_path / "mem.sqlite")
    memory.store.cache_clear()
    monkeypatch.setattr(tools, "DOSSIER", tmp_path / "dossier")
    monkeypatch.setattr(events, "TRACES", tmp_path / "traces")
    monkeypatch.setenv("ALLOWED_RECIPIENTS", "ops@example.com")
    yield tmp_path
    orchestrator.checkpointer.cache_clear()
    memory.store.cache_clear()


def test_send_waits_for_approval_then_runs(isolated):
    calls = [AIMessage(content="", tool_calls=[{"name": "send_playbook", "id": "c1",
                                                "args": {"building_id": BID, "recipient": "ops@example.com",
                                                         "depth_ft": 4}}]),
             AIMessage(content="Sent after approval.")]
    cb = orchestrator.SpendCallback("gemini-3.6-flash")
    agent = orchestrator.build_agent(BID, cb, model=FakeToolModel(messages=iter(calls)))
    trace = events.Trace(BID, "test")
    cfg = {"configurable": {"thread_id": "t1"}}
    events.activate(trace)
    try:
        for ns, chunk in agent.stream({"messages": [{"role": "user", "content": "send it"}]}, cfg,
                                      stream_mode="updates", subgraphs=True):
            events.translate(trace, ns, chunk)
        assert not (isolated / "dossier" / BID / "sends.json").exists()          # nothing sent yet
        assert [e["type"] for e in trace.events][-1] == "awaiting_approval"
        from langgraph.types import Command
        for ns, chunk in agent.stream(Command(resume={"decisions": [{"type": "approve"}]}), cfg,
                                      stream_mode="updates", subgraphs=True):
            events.translate(trace, ns, chunk)
    finally:
        events.activate(None)
    sent = json.loads((isolated / "dossier" / BID / "sends.json").read_text())
    assert sent[0]["approved"] and sent[0]["status"] == "not_sent"           # delivery is Phase 5B
    for e in trace.events:
        buildings.validate("agent_event", e)


def test_translate_plan_then_replan_and_delegation(isolated):
    t = events.Trace(BID, "t2")
    todo = lambda *xs: AIMessage(content="", tool_calls=[{"name": "write_todos", "id": "w", "args": {
        "todos": [{"content": x, "status": "pending"} for x in xs]}}])
    events.translate(t, (), {"model": {"messages": [todo("survey", "price")]}})
    events.translate(t, (), {"model": {"messages": [todo("survey", "price")]}})     # status-only: no new event
    events.translate(t, (), {"model": {"messages": [AIMessage(content="", tool_calls=[{"name": "task", "id": "k", "args": {
        "subagent_type": "site-scout", "description": "find doors"}}])]}})
    t.replan_pending = True
    events.translate(t, (), {"model": {"messages": [todo("re-price at 4 ft", "re-rank")]}})
    assert [e["type"] for e in t.events] == ["plan", "decision", "replan"]
    assert t.events[1]["text"].startswith("Delegate to site-scout")


def test_tools_run_on_cached_data(isolated):
    events.activate(events.Trace(BID, "t3"))
    try:
        ctx = json.loads(tools.get_site_context.invoke({"building_id": BID}))
        assert ctx["in_mapped_flood_zone"] is False
        pos = json.loads(tools.list_scan_positions.invoke({"building_id": BID}))
        assert sum(len(v) for v in pos["rooms"].values()) >= 3 and "cached" in pos["note"]
        sc = json.loads(tools.run_scenario.invoke({"building_id": BID, "depth_ft": 2}))
        assert sc["contents_usd"][0] <= sc["contents_usd"][1]
        rk = json.loads(tools.rank_mitigations.invoke({"building_id": BID, "depth_ft": 2}))
        assert rk["ranked"] and rk["ranked"][0]["rank"] == 1
    finally:
        events.activate(None)


def test_skill_files_have_frontmatter():
    files = orchestrator.skill_files()
    assert set(files) == {"/skills/survey/survey-method/SKILL.md", "/skills/loss/loss-method/SKILL.md"}
    for f in files.values():
        assert f["content"].startswith("---\nname: ")
