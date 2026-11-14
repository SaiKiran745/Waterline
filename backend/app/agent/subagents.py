"""The six subagents (AGENTS.md section 10). Each gets only its own tools, the relevant skill, and the dossier.

Subagent dicts follow deepagents 0.7.38 `SubAgent`: name, description, system_prompt, tools, skills.
"""
from app.agent.tools import ROLE_TOOLS

DOSSIER_RULE = ("Write a short markdown note of what you found to /dossier/{bid}/{name}.md with write_file "
                "(facts and numbers only, with the asset or entry-point ids). Then reply to the orchestrator in at most "
                "8 lines: findings, numbers as low-high ranges, and anything uncertain.")

SPECS = {
    "site-scout": dict(
        description="Finds where flood water gets into the building from Vexcel aerial imagery and FEMA/CoStar site "
                    "data. Give it the building id.",
        prompt="You are the site scout. Call get_site_context, then find_entry_points. Rank the openings by how easily "
               "water gets in, say which is the lowest door, and compare the door counts with CoStar.",
        skills=["/skills/survey/"]),
    "interior-surveyor": dict(
        description="Inventories what a flood would damage inside the building from its Matterport scan: chooses scan "
                    "positions, reads assets and heights, and re-looks at low-confidence assets. Give it the building id.",
        prompt="You are the interior surveyor. Follow the survey-method skill. Call list_scan_positions, choose positions "
               "with a reason each, call survey_positions once with all your choices, then call relook_asset for the "
               "low-confidence contents assets it reports (most valuable first, at most 4).",
        skills=["/skills/survey/"]),
    "market-analyst": dict(
        description="Pulls the CoStar building data behind the loss: property type, size, value basis, scan coverage. "
                    "Give it the building id.",
        prompt="You are the market analyst. Call get_building_value and explain the structure value basis in two "
               "sentences: where the value comes from and why only the scanned share counts.",
        skills=[]),
    "scenario-builder": dict(
        description="Prices the loss at a water depth: contents, structure and the assets hit. Give it the building id "
                    "and the depth in feet.",
        prompt="You are the scenario builder. Follow the loss-method skill. Call run_scenario at the depth you are given "
               "(and at any comparison depth you are asked for). Report ranges, the assets that drive the loss, and "
               "the placeholder assumptions.",
        skills=["/skills/loss/"]),
    "mitigation-planner": dict(
        description="Ranks fixes by payback at a depth: cost, avoided loss, payback note. Give it the building id and "
                    "the depth in feet.",
        prompt="You are the mitigation planner. Follow the loss-method skill. Call rank_mitigations at the depth you are "
               "given. If you are told about an earlier depth, say exactly which fixes moved up or down and why.",
        skills=["/skills/loss/"]),
    "communications": dict(
        description="Drafts the resilience report and the room-by-room pre-storm playbook for a depth. Give it the "
                    "building id and the depth. It never sends anything.",
        prompt="You are communications. Call draft_documents at the depth you are given. Then write a five-line summary "
               "for the property manager to /dossier/{bid}/communications.md: the depth, the loss range, the top three "
               "actions, and that vehicles should be moved. You never send anything; the orchestrator asks a person.",
        skills=[]),
}


def build(bid: str, middleware: list) -> list[dict]:
    out = []
    for name, s in SPECS.items():
        spec = {"name": name, "description": s["description"],
                "system_prompt": s["prompt"].replace("{bid}", bid) + "\n\n"
                                 + DOSSIER_RULE.replace("{bid}", bid).replace("{name}", name),
                "tools": ROLE_TOOLS[name], "middleware": list(middleware)}
        if s["skills"]:
            spec["skills"] = s["skills"]
        out.append(spec)
    return out
