"""Numbers guard (human decision 2026-11-14): every dollar figure in agent-written text must match a figure from a
tool result or a dossier file. A figure that matches nothing is removed and the removal is logged as a trace event.

Written text checked: the orchestrator's own messages (events.translate), the drafted report and playbook
(tools.draft_documents, tools.send_playbook and the /report and /playbook endpoints).

Matching: "$14,080-99,100" is two figures, 14,080 and 99,100; each must appear among the source numbers. A rounded
figure matches at the precision it is written in: "$75k" matches 75,300 (within 500), "$9.3k" matches 9,340 (within
50); "$73k" does not match 9,340. Source numbers are every number in the source texts, with or without "$".
"""
import bisect
import json
import re

NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"     # "14,080" or "14080"; "14080,99100" is two numbers
SUFFIX = r"(?:\s?(?:million|thousand|bn|k|K|m|M)\b)?"
MONEY = re.compile(rf"\$\s?(?P<a>{NUM})(?P<sa>{SUFFIX})(?:\s?(?:-|–|—|to)\s?\$?\s?(?P<b>{NUM})(?P<sb>{SUFFIX}))?")
PLAIN = re.compile(rf"(?<![\w.])(?P<n>{NUM})(?P<s>{SUFFIX})")
REMOVED = "[figure removed]"
SCALE = {"": 1, "k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "bn": 1e9}


def _value(num: str, suffix: str) -> tuple[float, float]:
    """(value, precision) of a written number: '9.3k' -> (9300, 100); '14,080' -> (14080, 1)."""
    num = num.replace(",", "")
    scale = SCALE[suffix.strip().lower()]
    decimals = len(num.split(".")[1]) if "." in num else 0
    precision = scale * 10 ** -decimals if scale > 1 else 1.0
    return float(num) * scale, precision


def numbers(texts) -> list[float]:
    """Every number in the source texts (sorted), so a written figure can be looked up."""
    out = set()
    for t in texts:
        t = t if isinstance(t, str) else json.dumps(t, default=str)
        for m in PLAIN.finditer(t):
            try:
                out.add(_value(m["n"], m["s"] or "")[0])
                out.add(float(m["n"].replace(",", "")))          # '75k' in a source also stands for 75
            except ValueError:
                continue
    return sorted(out)


def _known(v: float, precision: float, allowed: list[float]) -> bool:
    tol = precision / 2 + 0.5
    i = bisect.bisect_left(allowed, v - tol)
    return i < len(allowed) and allowed[i] <= v + tol


def scrub(text: str, sources) -> tuple[str, list[str]]:
    """Text with every unsourced dollar figure replaced by REMOVED, and the figures removed."""
    allowed = sources if isinstance(sources, list) and all(isinstance(x, float) for x in sources) else numbers(sources)
    removed: list[str] = []

    def check(m: re.Match) -> str:
        sa, sb = m["sa"] or "", m["sb"] or ""
        if m["b"] and not sa and sb:            # "$73-75k": the suffix belongs to both ends
            sa = sb
        ends = [_value(m["a"], sa)] + ([_value(m["b"], sb)] if m["b"] else [])
        if all(_known(v, p, allowed) for v, p in ends):
            return m.group(0)
        removed.append(m.group(0).strip())
        return REMOVED

    return MONEY.sub(check, text), removed


def guarded(text: str, sources, where: str, agent: str = "orchestrator") -> str:
    """scrub() and, if anything was removed, log one observation event naming the figures and where they were."""
    clean, removed = scrub(text, sources)
    if removed:
        from app.agent import events
        events.emit(agent, "observation",
                    f"Numbers guard: removed {len(removed)} dollar figure{'s' if len(removed) != 1 else ''} from {where} "
                    f"that no tool result or dossier file contains: {', '.join(removed[:6])}.",
                    data={"guard": "numbers", "where": where, "removed": removed})
    return clean


def document_sources(building: dict, assets: list[dict], depth_ft: float) -> list:
    """What the report and playbook may quote: the building record, the assets, and the scenario and ranked
    mitigations computed at that depth (the same results run_scenario and rank_mitigations return), each asset's
    expected loss, and the slider table's thresholds and standard-method comparison (contracts v1.3)."""
    from app import buildings
    from app.loss import mitigations as engine
    from app.loss import model, sim
    eps = buildings.get_entry_points(building["id"])
    ms = engine.ranked(building["id"], engine.candidates(building["id"], assets, eps), assets, depth_ft,
                       engine.building_loss_fn(building))
    from app.loss import grounding as ground
    table = model.scenario_table(building, assets)
    return [building, assets, model.scenario(building, assets, depth_ft), ms, ground.load(building["id"]) or {},
            sim.expected_by_asset(building, assets, depth_ft),
            {"thresholds": table["thresholds"], "standard_method": table["standard_method"]}]
