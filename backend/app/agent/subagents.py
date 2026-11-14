"""The six subagents (AGENTS.md section 10). Each gets only its own tools and the relevant skill.

Subagent dicts follow deepagents 0.7.38 `SubAgent`: name, description, system_prompt, tools, model, skills.
Their tools write the long results into the dossier themselves, so a subagent only calls its tools and replies.
"""
from app.agent.tools import ROLE_TOOLS

REPLY = "Reply to the orchestrator in at most 4 short lines: the key numbers as low-high ranges and anything uncertain."

SPECS = {
    "site-scout": dict(
        description="Finds where flood water gets in from Vexcel aerial imagery and FEMA/CoStar site data. Give it the "
                    "building id.",
        prompt="You are the site scout. Call get_site_context and find_entry_points (in parallel). Name the lowest "
               "door. If the aerial door count disagrees with CoStar, report the discrepancy as found; never pick one "
               "source silently.",
        skills=["/skills/survey/"]),
    "interior-surveyor": dict(
        description="Inventories what a flood would damage inside from the Matterport scan: chooses which scan "
                    "positions to read within a budget, then re-looks at low-confidence assets. Give it the building id.",
        prompt="You are the interior surveyor. Read the survey-method skill first. Then:\n"
               "1. Call list_scan_positions. Note the budget.\n"
               "2. Spread out: call survey_positions with about half the budget, positions far apart that cover every "
               "area (each end and the middle of the largest room, and each smaller room).\n"
               "3. Go deeper: from what each position saw, spend the rest of the budget on neighbouring positions "
               "('near' lists) around the positions that found the most contents. Skip areas that showed nothing.\n"
               "4. Call relook_asset for at most 3 low-confidence assets, most valuable first.\n"
               "Every reason names the area in plain words from what you saw or where it sits, for example 'warehouse "
               "bay next to the pallets seen earlier' or 'the other end of the largest room, not yet seen'. Never "
               "give coordinates or ids as the reason.",
        skills=["/skills/survey/"]),
    "market-analyst": dict(
        description="Pulls the CoStar building data behind the loss: type, size, value basis, scan coverage. Give it "
                    "the building id.",
        prompt="You are the market analyst. Call get_building_value. Say where the structure value comes from and "
               "why only the scanned share counts.",
        skills=[]),
    "scenario-builder": dict(
        description="Prices the loss at a water depth: contents, structure and the assets hit. Give it the building id "
                    "and the depth in feet.",
        prompt="You are the scenario builder. Call run_scenario at the depth you are given. Name the assets that "
               "drive the loss and the placeholder assumptions.",
        skills=["/skills/loss/"]),
    "mitigation-planner": dict(
        description="Ranks fixes by payback at a depth. Give it the building id, the depth in feet, and the earlier "
                    "depth if the depth changed.",
        prompt="You are the mitigation planner. Call rank_mitigations at the depth you are given. If you are told an "
               "earlier depth, say which fixes moved up or down and why (for example a 2 ft barrier stops helping "
               "above 2 ft).",
        skills=["/skills/loss/"]),
    "communications": dict(
        description="Drafts the resilience report and the room-by-room pre-storm playbook for a depth. Give it the "
                    "building id and the depth. It never sends anything.",
        prompt="You are communications. Call draft_documents at the depth you are given. You never send anything; "
               "the orchestrator asks a person.",
        skills=[]),
}


def build(bid: str, model=None) -> list[dict]:
    out = []
    for name, s in SPECS.items():
        spec = {"name": name, "description": s["description"],
                "system_prompt": s["prompt"] + f"\nThe building is {bid}.\n" + REPLY,
                "tools": ROLE_TOOLS[name]}
        if model is not None:
            spec["model"] = model
        if s["skills"]:
            spec["skills"] = s["skills"]
        out.append(spec)
    return out
