# Waterline: Devpost draft

**Tagline:** Flood maps stop at the front door. Waterline takes the water inside.

## Inspiration

Flood risk for a commercial building is usually a single answer: is the site inside FEMA's mapped flood zone or not? That answer says nothing about what a flood would ruin inside: the equipment on the floor, the stock on the lowest shelf, the electrical panel by the roll-up door. Five of our eight Houston buildings sit outside the mapped 1% annual-chance flood area, and in every one of them the survey found items whose lowest vulnerable part sits within 6 inches of the floor. CoStar's track gave us three layers that are rarely used together: CoStar building records, Matterport 3D scans of interiors and Vexcel aerial imagery. Together they can follow the water inside.

## What it does

Waterline is an AI agent for a commercial building's owner, manager, lender or insurer. For one of eight Houston buildings (named A to H), it:

- **Finds where water gets in.** It reads Vexcel aerial views, ranks the openings (grade-level drive-in doors first, dock-high doors last) and checks them against CoStar's door counts. On building E it saw 3 drive-in doors where CoStar records 4. It reports that discrepancy and lowers its confidence instead of picking one source.
- **Inventories what a flood would damage.** It walks the Matterport scan position by position and reads each panorama with a vision model. It measures each item's lowest vulnerable part by casting a ray onto the scan's 3D mesh, and looks again from a neighbouring position when confidence is low. On E it read all 49 positions and found 71 contents items worth about $225,000 (80% interval $176,000–292,000), plus 14 road vehicles listed separately as movable.
- **Prices the loss at a depth the user chooses.** Drag the slider and the water rises in the 3D model, hit items turn red and the loss updates.
  - **Figures:** every figure is a median with an 80% interval from 4,000 simulated draws of each item's value and height. On E: about $93,600 at 1 ft (80% interval $73,500–117,000) and about $297,000 at 4 ft ($235,000–367,000).
  - **The measured fact beside it,** with no dollar assumption: at 1 ft the water reaches 55–66 of E's 71 contents items.
  - **The Hazus comparison:** FEMA's Hazus contents curves on the same item values give about $37,900 at 1 ft. Ours is higher because Hazus averages over contents stored high, while the survey prices each item from its own measured height.
- **Ties the depth to real elevations, without pretending to model the flood.** The floor elevation is USGS ground plus an assumed slab allowance (NAVD 88), and FEMA's 1% flood level goes on the same scale.
  - E sits outside FEMA's zone, yet the 1% level on the creek 62 m away stays only about 1.3 ft below its floor, within the uncertainty.
  - On B the 1% level sits about 0.2 ft above the floor.
  - The ground in front of each door shows where water collects first.
- **Ranks a portfolio at the same storm, not just the same depth.** The map can put every building at FEMA's 1% flood level, plus 0 to 3 ft. Each building gets its own depth inside from its estimated floor, with a range.
  - **At FEMA's 1% level:** water gets inside 3 of 8 buildings. At +2 ft it is 7 of 8.
  - **The ranking changes with the question:** G loses most at the same depth inside, but ranks last at the same storm, because its dock-high floor sits 3.9 ft above the nearest FEMA level.
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
  - **Simulation:** 4,000 seeded draws give the median and 80% interval. Values are lognormal per item, items in a class move together, heights vary within their measured range, and structure varies between the Hazus curves.
  - **Elevation:** USGS 3DEP ground around each building, FEMA NFHL cross-section flood levels, and the NAVD 88 datum checked on both sides.
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
- **A full four-turn run on E costs about $0.12 and takes 55 seconds.** That covers assessing, re-planning, drafting and approval.
- **Honest numbers.** Every figure is a median with its 80% interval and its assumption ids; the worst-case sums are kept only as extreme bounds. Team-set values are shown as "assumed range, editable", and an audit lists the source of every number.

## Limits

- **Scanned area only.** Contents loss counts what the scan positions show. Four of the eight buildings are fully surveyed; the others read 13 to 15 positions, so their contents loss is a floor.
- **Assumptions:**
  - **Value ranges:** item values come from 15 team-set value classes, shown as "assumed range, editable", and a person can correct any of them.
  - **Simulation:** the 0.5 correlation within a class is a team-set assumption too. The 80% interval covers the stated value, height and structure uncertainty, not items the survey missed.
- **Elevation is approximate.** USGS states an accuracy of 0.53 m (1.74 ft) for its ground elevation. The floor is that ground plus an assumed slab allowance, so FEMA's level can fall either side of the floor for most buildings.
  - For buildings outside the zone, the FEMA level is the nearest mapped one; for H it is 1.4 km away.
- **No flood model.** The depth is a scenario tied to elevation. Waterline does not simulate rainfall, drainage or how water arrives.
- **One scan has no dollhouse view.** D's Matterport space refuses the dollhouse view, so the app opens its 3D model instead.

## What we learned

- Showing where a number comes from matters as much as the number.
- Small models are fast and cheap for tool calls, but they should never restate figures.
- A partial survey needs to say it is partial. "12 of 49 positions" changes how a reader should treat the total.
- A worst-case sum is not an uncertainty range. Adding every item's low end and every item's high end gave $24,758–219,063 for E at 1 ft. Simulating the same assumptions gives $73,500–117,000.
- A depth needs an anchor. Without the floor elevation and FEMA's level beside it, "1 ft of water" cannot be checked against anything.
- Picking a subset of scan positions did not beat chance: on E, 12 positions found 28–34% of the full survey's contents value, about what random sets of 12 found (27–31%), so we read every position.

## What's next

- Replace the assumed value ranges with sourced replacement costs and let owners upload their own asset lists.
- Measure door thresholds and slab height from the 3D scan, to replace the assumed slab allowance.
- Add Hurricane Harvey high-water marks as a reference level once the USGS flood-event service can be verified.
- Survey the remaining scan positions on the four partly surveyed buildings and add more cities.
- Connect the playbook to calendar and email so each step becomes an assigned task.

## Built with

Python, FastAPI, LangChain, deepagents, LangGraph, langchain-google-genai, Gemini 3.6 Flash, Gemini 3.5 Flash-Lite, SQLite, NumPy, Pillow, CoStar hackathon data, Matterport Model API, Vexcel imagery API, FEMA National Flood Hazard Layer, USGS Elevation Point Query Service, FEMA Hazus 6.1 damage functions, Next.js, React, TypeScript, three.js, Leaflet.

## For the CoStar judges (use of data, agentic depth, usefulness, demo)

- **Data:** Waterline combines all three CoStar-track layers, and each one changes the result.
  - The Matterport scan supplies the inventory and measured heights. Without it, a building falls back to "structure only" and is labelled so on the map.
  - CoStar supplies the assessor improvement value, the property type that picks the Hazus curve, and the door counts. The agent checks those counts against the aerial imagery, and they pick the slab allowance for the floor elevation.
  - Vexcel supplies the openings that set which barriers are offered and what they cost.
  - FEMA's flood levels and USGS ground elevations, on one datum (NAVD 88), turn the slider's depth into a water level outside. They also give the same-storm ranking, where the order of the buildings changes.
- **Agentic depth:** the agent plans, delegates, re-looks and re-plans, all visible in the live trace.
- **Usefulness:** the output is a ranked list of fixes with costs and a room-by-room playbook that a facilities manager could act on before a storm. It works for buildings outside the mapped flood zone, where no one is looking.

## For the Amazon Practical AI judges (creativity, usefulness, technical implementation, user experience)

- **Use case:** a pre-storm decision tool with a clear user (the people responsible for a commercial building) and a clear output (what to move, raise or block, and what each step saves).
- **Adaptive intelligence:**
  - A person corrects an asset's height or deletes a wrong one, and the correction goes to long-term memory.
  - The scenario and ranking update at once.
  - On the next run the agent applies the correction to similar items, explaining each item it includes or skips.
- **Technical implementation:**
  - the item heights come from the scan's 3D mesh
  - every number is a simulated median with an 80% interval and a source
  - the depth is tied to USGS and FEMA elevations on one datum
  - a guard stops the model inventing figures
- **User experience:** drag the slider and watch the water rise and the loss change, then approve the playbook with one click.

## For the LangChain judges (best use of deepagents)

- **Sub-agents:** one orchestrator and six specialist sub-agents, each with only its own tools; independent work runs in parallel.
- **Files:** every result is written to a per-building dossier (entry points, inventory, scenarios, mitigations, report, playbook), so tool messages stay short and the orchestrator's context stays small. The files are viewable through the API.
- **Skills:** the survey and loss methods are skills, loaded on demand by the sub-agent that needs them.
- **Memory:** human corrections persist in a SQLite store routed at `/memories/` and steer the next run.
- **Planning and approval:** `write_todos` drives the plan and re-plan, and the human-in-the-loop interrupt with a SQLite checkpointer pauses the send until a person approves.
- **Trace:** every step streams to the UI as an event, and the saved trace replays for the demo.
