"""Numbers guard: dollar figures in agent-written text must come from a tool result or dossier file."""
import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app import buildings
from app.actions import playbook, report
from app.agent import events, guard

SRC = ['{"contents_value_usd":"$9,340-75,300","value":[14080,99100]}']


def test_sourced_figures_stay_and_rounding_is_judged_at_its_precision():
    for text in ("Contents $9,340-75,300 at 1 ft.", "about $75k", "$9.3k to $75.3k", "$14,080–99,100"):
        assert guard.scrub(text, SRC) == (text, [])


def test_invented_figures_are_removed():
    clean, removed = guard.scrub("Contents $73k-$75k; total $1.2M; fix costs $14,000.", SRC)
    assert removed == ["$73k-$75k", "$1.2M", "$14,000"]
    assert "$" not in clean and clean.count(guard.REMOVED) == 3


def test_orchestrator_message_is_scrubbed_and_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "TRACES", tmp_path)
    t = events.Trace("building-e", "g1")
    events.activate(t)
    try:
        events.translate(t, ("tools:1",), {"tools": {"messages": [ToolMessage(SRC[0], tool_call_id="x", name="finish_survey")]}})
        events.translate(t, (), {"model": {"messages": [AIMessage(content="Contents $9,340-75,300; roughly $80k overall.")]}})
    finally:
        events.activate(None)
    said = [e for e in t.events if e["type"] == "decision"][-1]["text"]
    assert "$9,340-75,300" in said and "$80k" not in said and guard.REMOVED in said
    logged = [e for e in t.events if (e["data"] or {}).get("guard") == "numbers"]
    assert logged and logged[0]["data"]["removed"] == ["$80k"]
    for e in t.events:
        buildings.validate("agent_event", e)


@pytest.mark.parametrize("bid", sorted(buildings.building_ids()))
def test_every_report_and_playbook_figure_is_sourced(bid):
    b, a, e = buildings.get_building(bid), buildings.get_assets(bid), buildings.get_entry_points(bid)
    for d in (1, 4):
        src = guard.numbers(guard.document_sources(b, a, d))
        for r in (report, playbook):
            assert guard.scrub(r.render(b, a, e, d), src)[1] == []
