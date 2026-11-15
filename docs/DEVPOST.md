# Waterline

**Flood maps stop at the front door. Waterline takes the water inside.**

Waterline is an AI agent that works out what a flood would ruin inside a commercial building, what that would cost, and what to do about it before the storm. It runs on eight Houston buildings, named A to H.

## Inspiration

Flood risk for a commercial building usually comes down to one answer: is the site inside FEMA's mapped flood zone or not? That answer says nothing about what a flood would ruin inside: the machine on the floor, the stock on the lowest shelf, the electrical panel by the roll-up door.

Five of our eight buildings sit outside FEMA's 1% annual-chance flood area. In every one of them, the survey found an item whose lowest vulnerable part sits within 2 inches of the floor.

The CoStar track offered three layers that are rarely used together: CoStar building records, Matterport 3D scans of interiors and Vexcel aerial imagery. Together they can follow the water inside.

## What it does

Waterline is for the people who own, manage, lend against or insure a building. For each building it:

- **Finds where water gets in.**
  - It reads Vexcel aerial views and ranks the openings: grade-level drive-in doors first, dock-high doors last.
  - It checks them against CoStar's door counts. On E it sees 3 drive-in doors where CoStar records 4, so it reports the discrepancy and lowers its confidence instead of picking one source.
- **Inventories what a flood would damage.**
  - It walks the Matterport scan position by position and reads each panorama with a vision model.
  - It measures each item's lowest vulnerable part by casting a ray onto the scan's 3D mesh, and looks again from a neighbouring position when its confidence is low.
  - On E it read all 49 positions and found 71 contents items worth about $225,000 (80% range $176,000–292,000). Fourteen road vehicles are listed separately as movable.
- **Prices the loss at a depth the user chooses.** Drag the slider and the water rises inside the 3D model, hit items turn red and the loss updates.
  - **Median with an 80% range.** Every dollar figure comes from 4,000 simulated draws of each item's value and height. On E: about $93,600 at 1 ft (80% range $73,500–117,000) and about $297,000 at 4 ft ($235,000–367,000).
  - **Measured counts, with no dollar assumption.** At 1 ft the water reaches 55–66 of E's 71 contents items. Across all eight buildings, 288 of 380 surveyed items (76%) have heights measured from the mesh.
  - **The standard method beside ours.** FEMA's Hazus 6.1 contents curves, applied to the same item values, give about $37,900 for E at 1 ft against our $72,200. Ours is 1.5–2.3 times Hazus on E and B from 1 to 6 ft. Hazus averages over a whole building's contents, including stock stored high; the survey prices each item from its own height.
- **Ties each depth to real elevations, without pretending to model the flood.**
  - The floor elevation is USGS ground plus an assumed slab allowance, in ft NAVD 88. FEMA's 1% flood level goes on the same scale.
  - E sits outside FEMA's zone, yet the 1% level on the stream 62 m away is only about 1.3 ft below its floor (range −3.6 to +1.0 ft).
  - On B the 1% level sits about 0.2 ft above the floor.
  - The ground in front of each door shows where water collects first.
- **Ranks the portfolio at the same storm, not only at the same depth.**
  - The map can put every building at FEMA's 1% flood level, plus 0 to 3 ft. Each building gets its own depth inside from its estimated floor, with a range.
  - At FEMA's 1% level, water gets inside 3 of the 8 buildings; at +1 ft, 4; at +2 and +3 ft, 7.
  - The question changes the answer. G loses the most at the same depth inside, but ranks last at the same storm: it is dock-high, and its floor sits 3.9 ft above the nearest FEMA level.
- **Ranks fixes by payback and re-plans when the scenario changes.** When the depth moves from 1 ft to 4 ft, the agent re-plans and says what moved. On E the 2 ft barriers drop out of the top three, and moving office stock onto racking rises from third to second.
- **Writes a resilience report and a room-by-room pre-storm playbook.** It sends the playbook only after a person clicks Approve, and only to an allowed address.
- **Learns from corrections.** A person corrects one desk: "desks here are steel-frame on legs; the wooden drawers start 1.5 ft up". The agent remembers it, applies it to the matching desks on the next run, and says which look-alikes it skipped and why.

## How we built it

- **Back end:** Python and FastAPI. Every external response is cached, so the whole demo runs from cache with the network off.
- **Agent:**
  - LangChain's `deepagents` 0.7.38. The orchestrator runs on Gemini 3.6 Flash; six sub-agents run on Gemini 3.5 Flash-Lite: site scout, interior surveyor, market analyst, scenario builder, mitigation planner and communications.
  - It plans with `write_todos`, keeps a per-building dossier of files, loads two skills on demand (survey method, loss method), keeps human corrections in long-term memory and pauses for approval before sending.
- **Survey:**
  - Gemini vision reads the Matterport panoramas.
  - We calibrated the panorama-to-mesh geometry ourselves, so heights come from the scan's own 3D mesh wherever it resolves the item.
  - A privacy screen withholds any panorama face that shows identifiable people, children's spaces or personal documents.
- **Loss model:**
  - Contents damage is gradual: an item's share of value lost rises with depth until it is a total loss. Values come from 15 value classes.
  - Structure loss uses FEMA Hazus 6.1 depth-damage curves, applied to the CoStar assessor improvement value and scaled to the scanned share of the building.
  - The simulation runs 4,000 seeded draws. Values are lognormal per item, items in a class move together (correlation 0.5), heights vary within their measured range and structure varies between the Hazus curves. Every draw is evaluated at every depth, so no figure falls as the water rises.
- **Elevation:** USGS 3DEP ground around each building and in front of each door, and FEMA flood-map cross-section levels, with the NAVD 88 datum checked on both sides.
- **Front end:** Next.js and React. three.js draws the water inside the Matterport mesh, Matterport's Bundle SDK shows the photo-real view, and Leaflet draws the portfolio map.
- **Live trace:** every plan, decision, tool call, file write and approval wait streams to the UI and is saved for replay.

## Challenges we ran into

- **Small models paraphrase numbers.** Flash-Lite restated "$9,340–75,300" as "$73k–75k" and invented costs.
  - We made each sub-agent's reply its tool's exact output.
  - We added a numbers guard: any dollar figure the agent writes that matches no tool result is removed, and the removal is logged in the trace.
- **Mapping panoramas to the mesh.** Turning a pixel in a panorama into a point on the 3D mesh took a calibration pass before heights could be trusted.
- **Order-dependent results.** The same 49 positions gave 71 or 73 items depending on read order. We fixed the merge order so a survey is reproducible.
- **Honest ranges.** Summing every item's low end and every item's high end gave E $24,758–219,063 at 1 ft, a range too wide to act on. Simulating the same assumptions gives $73,500–117,000.
- **No floor elevations.** None of the data gives a floor height, so we built one from USGS ground plus a slab allowance chosen from the door types (drive-in, dock-high or pedestrian) seen in the aerial images and recorded by CoStar, and carried the USGS error into every range.

## Accomplishments that we're proud of

- **All three data layers change the answer.** Matterport gives what is inside and how high, CoStar gives what it is worth and checks the door count, and Vexcel gives where water enters.
- **The agent visibly reasons.** It plans, splits work across six specialists, re-looks at uncertain items, re-plans when the depth changes, applies a person's correction to similar items and stops for approval.
- **It is cheap and fast.** A full four-turn run on E (assess, re-plan, draft, approve) costs about $0.12 and takes about 55 seconds.
- **The numbers are honest.** Every figure is a median with its 80% range and its assumption ids, beside a measured count that needs no dollar assumption and a standard-method comparison. Team-set values are labelled "assumed range, editable", and an audit lists the source of every number.

## What we learned

- Showing where a number comes from matters as much as the number.
- Small models are fast and cheap for tool calls, but they should never restate figures.
- A partial survey has to say it is partial. "13 of 57 positions read" changes how a reader should treat the total.
- A worst-case sum is not an uncertainty range.
- A depth needs an anchor. Without the floor elevation and FEMA's level beside it, "1 ft of water" cannot be checked against anything.
- Picking a subset of scan positions did not beat chance. On E, 12 chosen positions found 28–34% of the full survey's contents value, about what random sets of 12 found (27–31%). So we read every position.

## Limits

- **Scanned area only.** Contents loss counts what the scan positions show. B, D, E and G are fully surveyed. A, C, F and H read 13 to 15 positions each, so their contents loss is a floor, not a whole-building estimate.
- **Value ranges are assumptions.** The 15 value classes, the mitigation costs and the 0.5 correlation within a class are set by the team, shown as "assumed range, editable", and correctable by a person.
- **The 80% range covers only the stated uncertainty:** values, heights and the Hazus structure range. It does not cover items the survey missed.
- **Elevation is approximate.** USGS states an accuracy (RMSE) of 0.53 m (1.74 ft) for its ground elevation. The floor is that ground plus an assumed slab allowance, so for most buildings FEMA's level could fall on either side of the floor. For buildings outside the zone, the FEMA level is the nearest mapped one; for H it is 1.4 km away.
- **No flood model.** A depth is a scenario tied to elevation, not a forecast. Waterline does not simulate rainfall, drainage or how water arrives, and the same-storm ranking compares buildings at FEMA's level rather than forecasting any storm.
- **Door thresholds are not measured.** The ground in front of each door is measured; the slab height above it is assumed.
- **One scan has no dollhouse view.** D's Matterport space refuses that view, so the app opens D's 3D model instead.

## What's next

- Replace the assumed value ranges with sourced replacement costs, and let owners upload their own asset lists.
- Measure door thresholds and slab height from the 3D scan, to replace the assumed slab allowance.
- Add Hurricane Harvey high-water marks as a reference level once the USGS flood-event service can be verified.
- Survey the remaining scan positions on A, C, F and H, and add more cities.
- Connect the playbook to calendar and email so each step becomes an assigned task.

## Built with

Python, FastAPI, NumPy, Pillow, SQLite, LangChain, deepagents, LangGraph, langchain-google-genai, Gemini 3.6 Flash, Gemini 3.5 Flash-Lite, Next.js, React, TypeScript, three.js, Leaflet, CoStar hackathon data, Matterport Model API, Matterport Bundle SDK, Vexcel imagery API, FEMA National Flood Hazard Layer, FEMA Hazus 6.1 damage functions, USGS 3DEP via the Elevation Point Query Service.

## For the CoStar judges

Waterline uses all three track layers, and removing any one changes the answer. Matterport supplies the inventory and the measured heights; without it a building falls back to "structure only", and the map says so. CoStar supplies the assessor value behind structure loss, the property type that picks the Hazus curve, and the door counts. The agent checks those counts against the aerial imagery, and the door types, from both sources, set the slab allowance for the floor elevation. Vexcel supplies the openings that decide which barriers are offered and what they cost. Public FEMA and USGS elevations, on one datum, turn the slider depth into a water level outside, and they reorder the portfolio: G goes from first to last. The agent's plan, delegation, re-looks and re-plan are all visible in the live trace. The output is a ranked list of fixes with costs and a room-by-room playbook that a facilities manager could act on before a storm, including for buildings outside the mapped zone, where no one is looking.

## For the Amazon Practical AI judges

The user and the use case are concrete: the people responsible for a commercial building, deciding what to move, raise or block before a storm, and what each step saves. Waterline adapts to feedback. A person corrects an item's height or deletes a wrong one, the loss and the ranking update at once, and on the next run the agent applies the correction to similar items, explaining each item it includes or skips. Technically, item heights come from the scan's 3D mesh, every figure is a simulated median with an 80% range and a source, depths are tied to USGS and FEMA elevations, and a guard stops the model inventing figures. The experience fits in one gesture: drag the slider, watch the water rise inside the building and the loss change, then approve the playbook with one click.

## For the LangChain judges

Waterline uses the deepagents harness throughout. One orchestrator delegates to six specialist sub-agents, each with only its own tools, and independent work runs in parallel. Every result goes to a per-building file dossier (entry points, inventory, scenarios, fixes, report, playbook), so tool messages and the orchestrator's context stay small, and the files can be read through the API. The survey and loss methods are skills that a sub-agent loads only when it needs them. Human corrections persist in a SQLite memory store at `/memories/` and steer the next run. `write_todos` drives the plan and the re-plan, and the human-in-the-loop interrupt, with a SQLite checkpointer, holds the send until a person approves. Every step streams to the UI as an event, and the saved trace replays for the demo.
