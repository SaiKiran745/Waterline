"""The six subagents (AGENTS.md section 10). Each gets only its own tools and the relevant skill.

Subagent dicts follow deepagents 0.7.38 `SubAgent`: name, description, system_prompt, tools, model, skills.
Their tools write the long results into the dossier themselves, so a subagent only calls its tools and replies.
"""
from langchain.agents.middleware import AgentMiddleware, ModelResponse
from langchain_core.messages import AIMessage, ToolMessage

from app.agent.tools import FINAL_TOOLS, ROLE_TOOLS


class EchoFinalTool(AgentMiddleware):
    """When a subagent's final tool has just answered, reply with that exact result instead of calling the model.

    deepagents returns a subagent's last AI message to the orchestrator. Letting the model restate tool output
    garbled numbers (3.5 Flash-Lite turned $9,340-75,300 into "$73k-$75k" and invented costs), so the reply is the
    tool's own text: exact, and one model call cheaper.
    """

    def wrap_model_call(self, request, handler):
        msgs = request.messages
        tail = []
        for m in reversed(msgs):
            if not isinstance(m, ToolMessage):
                break
            tail.append(m)
        if tail and any(m.name in FINAL_TOOLS for m in tail):
            text = "\n".join(m.text if isinstance(m.text, str) else str(m.content) for m in reversed(tail)
                             if m.name in FINAL_TOOLS)
            return ModelResponse(result=[AIMessage(content=text)])
        return handler(request)

REPLY = "Reply to the orchestrator in at most 4 short lines: the key numbers as low-high ranges and anything uncertain."

SPECS = {
    "site-scout": dict(
        description="Finds where flood water gets in from Vexcel aerial imagery and FEMA/CoStar site data. Give it the "
                    "building id.",
        prompt="You are the site scout. Call find_entry_points; its exact result is your reply "
               "(including any discrepancy with CoStar's door counts).",
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
               "5. Call finish_survey last; its exact result is your reply.\n"
               "Reasons: plain words naming the area. Before you have seen an area, say only where it is ('the other "
               "end of the largest room, not yet seen'); never guess what it contains. After a survey call, use the "
               "names in areas_now (for example 'warehouse middle, next to the pallets seen at the east end'). Never "
               "give coordinates or ids as the reason.",
        skills=["/skills/survey/"]),
    "market-analyst": dict(
        description="Pulls the CoStar building data behind the loss: type, size, value basis, scan coverage. Give it "
                    "the building id.",
        prompt="You are the market analyst. Call get_building_value; its exact result is your reply.",
        skills=[]),
    "scenario-builder": dict(
        description="Prices the loss at a water depth: contents, structure and the assets hit. Give it the building id "
                    "and the depth in feet.",
        prompt="You are the scenario builder. Call run_scenario at the depth you are given; its exact result is your reply.",
        skills=["/skills/loss/"]),
    "mitigation-planner": dict(
        description="Ranks fixes by payback at a depth. Give it the building id, the depth in feet, and the earlier "
                    "depth if the depth changed.",
        prompt="You are the mitigation planner. Call rank_mitigations at the depth you are given, with "
               "previous_depth_ft if you are told an earlier depth; its exact result is your reply.",
        skills=["/skills/loss/"]),
    "communications": dict(
        description="Drafts the resilience report and the room-by-room pre-storm playbook for a depth. Give it the "
                    "building id and the depth. It never sends anything.",
        prompt="You are communications. Call draft_documents at the depth you are given; its exact result is your reply. You never send anything; the orchestrator asks a person.",
        skills=[]),
}


def build(bid: str, model=None) -> list[dict]:
    out = []
    for name, s in SPECS.items():
        spec = {"name": name, "description": s["description"],
                "system_prompt": s["prompt"] + f"\nThe building is {bid}.\n" + REPLY,
                "tools": ROLE_TOOLS[name], "middleware": [EchoFinalTool()]}
        if model is not None:
            spec["model"] = model
        if s["skills"]:
            spec["skills"] = s["skills"]
        out.append(spec)
    return out
