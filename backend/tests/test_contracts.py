"""Fixtures validate against contracts/ and obey the AGENTS.md section 9 loss rule."""
import json

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from app import fixtures
from app.config import CONTRACTS, FIXTURES

PAIRS = [("building", "building.json"), ("entry_point", "entry_points.json"), ("asset", "assets.json"),
         ("scenario_result", "scenario_2ft.json"), ("scenario_result", "scenarios.json"),
         ("mitigation", "mitigations.json"), ("agent_event", "agent_events.json"),
         ("scenario_table", "scenario_table.json"), ("triage", "triage.json"), ("grounding", "grounding.json")]


@pytest.mark.parametrize("schema,fixture", PAIRS)
def test_fixture_matches_schema(schema, fixture):
    s = json.loads((CONTRACTS / f"{schema}.schema.json").read_text())
    Draft202012Validator.check_schema(s)
    data = json.loads((FIXTURES / fixture).read_text())
    items = data if isinstance(data, list) and s.get("type") != "array" else [data]
    v = Draft202012Validator(s, format_checker=FormatChecker())
    errors = [f"{list(e.path)} {e.message}" for it in items for e in v.iter_errors(it)]
    assert not errors, errors[:5]


def test_fixture_sizes():
    assert len(fixtures.load("assets.json")) == 25
    assert len({a["room"] for a in fixtures.load("assets.json")}) == 5
    assert len(fixtures.load("entry_points.json")) == 3
    assert [s["depth_ft"] for s in fixtures.load("scenarios.json")] == [0, 1, 2, 4, 8]
    assert len({m["id"] for m in fixtures.load("mitigations.json")}) == 5
    assert len(fixtures.load("agent_events.json")) == 40
    assert {"plan", "decision", "replan", "awaiting_approval"} <= {e["type"] for e in fixtures.load("agent_events.json")}


def test_computed_scenarios_equal_fixture_scenarios():
    for s in fixtures.load("scenarios.json"):
        assert fixtures.scenario(s["depth_ft"]) == s


def test_zero_depth_zero_loss():
    s = fixtures.scenario(0)
    assert s["loss_usd_low"] == s["loss_usd_high"] == s["structure_loss_usd_low"] == s["structure_loss_usd_high"] == 0
    assert s["assets_hit"] == []


def test_loss_monotonic_and_low_not_above_high():
    prev = None
    for q in range(0, 33):
        s = fixtures.scenario(q / 4)
        assert s["loss_usd_low"] <= s["loss_usd_high"]
        assert s["structure_loss_usd_low"] <= s["structure_loss_usd_high"]
        if prev:
            for k in ("loss_usd_low", "loss_usd_high", "structure_loss_usd_low", "structure_loss_usd_high"):
                assert s[k] >= prev[k], (q / 4, k)
        prev = s


def test_fixture_scenario_table_matches_endpoint_and_scenarios():
    t = fixtures.load("scenario_table.json")
    assert t == fixtures.scenario_table()
    for s in fixtures.load("scenarios.json"):
        row = t["rows"][t["steps_ft"].index(s["depth_ft"])]
        assert (row["loss_usd_low"], row["loss_usd_high"]) == (s["loss_usd_low"], s["loss_usd_high"])
