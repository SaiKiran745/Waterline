# Waterline: Devpost draft

**Tagline:** Flood maps stop at the front door. Waterline takes the water inside.

## Inspiration

Flood risk for a commercial building is usually a single answer: is the site inside FEMA's mapped flood zone or not? That answer says nothing about what a flood would ruin inside: the equipment on the floor, the stock on the lowest shelf, the electrical panel by the roll-up door. Five of our eight Houston buildings sit outside the mapped 1% annual-chance flood area, and in every one of them the survey found items whose lowest vulnerable part sits within 6 inches of the floor. CoStar's track gave us three layers that are rarely used together: CoStar building records, Matterport 3D scans of interiors and Vexcel aerial imagery. Together they can follow the water inside.

## What it does

Waterline is an AI agent for a commercial building's owner, manager, lender or insurer. For one of eight Houston buildings (named A to H), it:

- **Finds where water gets in.** It reads Vexcel aerial views, ranks the openings (grade-level drive-in doors first, dock-high doors last) and checks them against CoStar's door counts. On building E it saw 3 drive-in doors where CoStar records 4. It reports that discrepancy and lowers its confidence instead of picking one source.
- **Inventories what a flood would damage.** It walks the Matterport scan position by position and reads each panorama with a vision model. It measures each item's lowest vulnerable part by casting a ray onto the scan's 3D mesh, and looks again from a neighbouring position when confidence is low. On E it read all 49 positions and found 71 contents items worth $81,260–431,200, plus 14 road vehicles listed separately as movable.
- **Prices the loss at a depth the user chooses.** Drag the slider and the water rises in the 3D model, hit items turn red and the loss range updates. On E: $24,412–215,850 at 1 ft and $108,954–543,580 at 4 ft. Every figure is a low–high range, and every assumption is listed.
- **Ranks fixes by payback, and re-plans when the scenario changes.** When the depth moves from 1 ft to 4 ft, the agent re-plans and says what moved. On E, the 2 ft barriers stop helping, and moving office stock onto racking rises from rank 3 to rank 2.
- **Writes a resilience report and a room-by-room pre-storm playbook.** It sends the playbook only after a person clicks Approve, and only to an allowed address.
- **Learns from corrections.** When a person corrects an asset ("desks here are steel-frame on legs; the wooden drawers start 1.5 ft up"), the agent remembers it. On the next run it applies it to the matching desks and says which look-alikes it skipped and why.

## How we built it

- **Back end:** Python and FastAPI.
- **Agent:**
  - LangChain's `deepagents` 0.7.38 on Gemini 3.6 Flash, with six sub-agents on Gemini 3.5 Flash-Lite: site scout, interior surveyor, market analyst, scenario builder, mitigation planner and communications.
  - The agent plans with `write_todos` and keeps a per-building dossier of files.
  - It loads two skills on demand: the survey method and the loss method.
  - It stores human corrections in long-term memory and pauses for approval before sending.
- **Survey:**
  - Gemini vision reads the Matterport panoramas.
  - We calibrated the panorama-to-mesh geometry ourselves, so heights come from the scan's own 3D mesh where it resolves the item.
  - A privacy screen hides any panorama face with identifiable people, children's spaces or personal documents.
- **Loss model:**
  - Gradual contents damage per value class: the item's share of value lost rises with water depth until it is a total loss.
  - Structure loss from FEMA Hazus 6.1 depth-damage curves, applied to the CoStar assessor improvement value and scaled to the scanned share of the building.
- **Front end:** Next.js, three.js for the water inside the Matterport mesh, Leaflet for the triage map.
- **Live trace:** every plan, decision, tool call, file write and approval wait is streamed to the UI.
- **Caching:** everything external is cached, so the whole demo runs from cache with the network off.

## Challenges we ran into

- **Small models paraphrase numbers.** Flash-Lite restated "$9,340–75,300" as "$73k–75k" and invented costs. We made each sub-agent's reply its tool's exact output. We also added a numbers guard: any dollar figure the agent writes that matches no tool result is removed, and the removal is logged in the trace.
- **Mapping panoramas to the mesh.** Turning a pixel in a panorama face into a point on the 3D mesh took a calibration pass before heights could be trusted.
- **Order-dependent results.** The same 49 positions gave 71 or 73 assets depending on read order. We fixed the merge order so a building's survey is reproducible.

## Accomplishments that we're proud of

- **All three data layers change the answer.** Matterport gives what and how high, CoStar gives what it is worth and checks the door count, and Vexcel gives where water enters.
- **The agent visibly reasons.** It plans, splits work across six specialists, re-looks at uncertain items, re-plans when the depth changes, applies a person's correction to similar items and stops for approval.
- **A full four-turn run on E costs about $0.13 and takes 48 seconds.** That covers assessing, re-planning, drafting and approval.
- **Honest numbers.** Every figure is a range with its assumption ids. Team-set values are shown as "assumed range, editable", and an audit lists the source of every number.

## What we learned

- Showing where a number comes from matters as much as the number.
- Small models are fast and cheap for tool calls, but they should never restate figures.
- A partial survey needs to say it is partial. "12 of 49 positions" changes how a reader should treat the total.
- Picking a subset of scan positions did not beat chance: on E, 12 positions found 28–34% of the full survey's contents value, about what random sets of 12 found (27–31%), so we read every position.

## What's next

- Replace the assumed value ranges with sourced replacement costs and let owners upload their own asset lists.
- Measure door thresholds and slab height from the 3D scan, so the depth inside is tied to water outside.
- Survey the remaining scan positions on the six partly surveyed buildings and add more cities.
- Connect the playbook to calendar and email so each step becomes an assigned task.

## Built with

Python, FastAPI, LangChain, deepagents, LangGraph, langchain-google-genai, Gemini 3.6 Flash, Gemini 3.5 Flash-Lite, SQLite, NumPy, Pillow, CoStar hackathon data, Matterport Model API, Vexcel imagery API, FEMA National Flood Hazard Layer, USGS Elevation Point Query Service, FEMA Hazus 6.1 damage functions, Next.js, React, TypeScript, three.js, Leaflet.

## For the CoStar judges (use of data, agentic depth, usefulness, demo)

- **Data:** Waterline combines all three CoStar-track layers, and each one changes the result.
  - The Matterport scan supplies the inventory and measured heights. Without it, a building falls back to "structure only" and is labelled so on the map.
  - CoStar supplies the assessor improvement value, the property type that picks the Hazus curve, and the door counts the agent checks against the aerial imagery.
  - Vexcel supplies the openings that set which barriers are offered and what they cost.
- **Agentic depth:** the agent plans, delegates, re-looks and re-plans, all visible in the live trace.
- **Usefulness:** the output is a ranked list of fixes with costs and a room-by-room playbook that a facilities manager could act on before a storm. It works for buildings outside the mapped flood zone, where no one is looking.

## For the Amazon Practical AI judges (creativity, usefulness, technical implementation, user experience)

- **Use case:** a pre-storm decision tool with a clear user (the people responsible for a commercial building) and a clear output (what to move, raise or block, and what each step saves).
- **Adaptive intelligence:**
  - A person corrects an asset's height or deletes a wrong one, and the correction goes to long-term memory.
  - The scenario and ranking update at once.
  - On the next run the agent applies the correction to similar items, explaining each item it includes or skips.
- **Technical implementation:** the item heights come from the scan's 3D mesh, every number has a range and a source, and a guard stops the model inventing figures.
- **User experience:** drag the slider and watch the water rise and the loss change, then approve the playbook with one click.

## For the LangChain judges (best use of deepagents)

- **Sub-agents:** one orchestrator and six specialist sub-agents, each with only its own tools; independent work runs in parallel.
- **Files:** every result is written to a per-building dossier (entry points, inventory, scenarios, mitigations, report, playbook), so tool messages stay short and the orchestrator's context stays small. The files are viewable through the API.
- **Skills:** the survey and loss methods are skills, loaded on demand by the sub-agent that needs them.
- **Memory:** human corrections persist in a SQLite store routed at `/memories/` and steer the next run.
- **Planning and approval:** `write_todos` drives the plan and re-plan, and the human-in-the-loop interrupt with a SQLite checkpointer pauses the send until a person approves.
- **Trace:** every step streams to the UI as an event, and the saved trace replays for the demo.
