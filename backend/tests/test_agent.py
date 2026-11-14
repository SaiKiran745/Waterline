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
    from app.actions import send as send_action
    monkeypatch.setattr(send_action, "LOG_DIR", tmp_path / "dossier")
    for k in send_action.SETTINGS:
        monkeypatch.delenv(k, raising=False)
    tools.reset(BID)
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
    assert sent[0]["approved"] and sent[0]["status"] == "draft_only"         # no SMTP settings: draft only
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


def _call(t, **args):
    """Invoke a tool the way the agent does (tools that write dossier files need a tool-call id)."""
    out = t.invoke({"type": "tool_call", "id": "tc1", "name": t.name, "args": args})
    if hasattr(out, "update"):                                    # Command: short message + dossier files
        return json.loads(out.update["messages"][0].content), out.update.get("files", {})
    return json.loads(out.content if hasattr(out, "content") else out), {}


def test_tools_run_on_cached_data(isolated):
    events.activate(events.Trace(BID, "t3"))
    try:
        ctx, _ = _call(tools.get_site_context, building_id=BID)
        assert ctx["in_1pct_zone"] is False
        pos, _ = _call(tools.list_scan_positions, building_id=BID)
        assert pos["mode"].startswith("full survey") and pos["areas"][0]["id"] == "A1"
        sizes = [a["positions"] for a in pos["areas"]]
        assert sizes == sorted(sizes, reverse=True) and [a["to_read"] for a in pos["areas"]] == sizes
        sc, files = _call(tools.run_scenario, building_id=BID, depth_ft=2)
        assert sc["details"] in files and "Contents" in files[sc["details"]]["content"]
        rk, files = _call(tools.rank_mitigations, building_id=BID, depth_ft=2)
        assert rk["top"][0].startswith("1. ") and rk["details"] in files
        ep, files = _call(tools.find_entry_points, building_id=BID)
        assert ep["discrepancies"] and "CoStar records 4" in ep["discrepancies"][0]
        types = [e["type"] for e in events.current().events]
        assert types.count("artifact") == 3                           # one per dossier file written
    finally:
        events.activate(None)


def test_skill_files_have_frontmatter():
    files = orchestrator.skill_files()
    assert set(files) == {"/skills/survey/survey-method/SKILL.md", "/skills/loss/loss-method/SKILL.md"}
    for f in files.values():
        assert f["content"].startswith("---\nname: ")


def test_rerank_explains_what_moved_without_the_model(isolated):
    events.activate(events.Trace(BID, "t5"))
    try:
        rk, _ = _call(tools.rank_mitigations, building_id=BID, depth_ft=4, previous_depth_ft=1)
        assert rk["changed_since_previous_depth"], rk
        assert {"rank_mitigations", "finish_survey"} <= tools.FINAL_TOOLS
        assert any(e["type"] == "decision" and e["text"].startswith("Priority change 1 -> 4 ft")
                   for e in events.current().events)
    finally:
        events.activate(None)


def test_quick_scan_splits_the_budget_by_area_size():
    assert tools.quota([27, 8, 4, 3, 3, 3, 1], None) == [27, 8, 4, 3, 3, 3, 1]       # default: every position
    q = tools.quota([27, 8, 4, 3, 3, 3, 1], 12)
    assert sum(q) == 12 and q[0] == max(q) and q == sorted(q, reverse=True)
    assert tools.quota([11], 12) == [11]


def test_stored_survey_never_shrinks(isolated, monkeypatch):
    """A batch that reads one small area still leaves every stored position in the survey."""
    from app.survey import interior
    before = {p["location_id"] for p in interior.stored_read(BID)}
    if not before or not interior.vision_index(BID) >= before:
        pytest.skip("needs a stored survey with cached vision answers")
    import shutil
    d = buildings.BUILDINGS / BID
    keep = {f: (d / f).read_bytes() for f in ("assets.json", "asset_geometry.json", "survey_log.json", "screening.json")
            if (d / f).exists()}
    monkeypatch.setitem(tools.SETTINGS, "cached_positions_only", True)
    events.activate(events.Trace(BID, "t6"))
    try:
        out, _ = _call(tools.survey_area, building_id=BID, area_ids=["A7"], reason="the smallest room, as a test")
        assert out["stored_survey"].startswith(f"{len(before)} of ")
        assert {p["location_id"] for p in interior.stored_read(BID)} >= before
    finally:
        events.activate(None)
        for f, b in keep.items():
            (d / f).write_bytes(b)
