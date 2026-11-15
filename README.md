# Waterline

Flood maps stop at the front door. Waterline takes the water inside.

Waterline is an AI agent that estimates what a flood would destroy inside a commercial building. For a building in Houston it:

1. finds where water gets in, from aerial imagery;
2. walks the building's 3D scan and lists what sits low enough to flood, with a height and a confidence for each item;
3. prices the loss at a water depth the user chooses, using CoStar building data;
4. ranks fixes by payback;
5. writes a resilience report and a room-by-room pre-storm playbook, and sends the playbook only after a person approves.

Built for HackPrinceton Fall 2026 (CoStar track).

**Who it is for**
- People who own, manage or lend against light-industrial and flex buildings.
- Their insurers.

A FEMA map says whether a site is in a flood zone. It does not say which equipment and stock sit low enough to flood, what that would cost, or which fixes pay back first. Building E is outside the mapped flood zone, and at 1 ft of water inside it still loses $24,412–215,850.

- Brief for coding agents: `AGENTS.md` (copied to `CLAUDE.md`)
- Data shapes: `contracts/README.md`
- What each data source offers: `docs/DATA_NOTES.md`
- Decisions: `docs/DECISIONS.md`
- Every number and its source: `docs/AUDIT.md`

## How it works

```
                      +---------------------------- Next.js front end ----------------------------+
                      |  triage map | aerial view | 3D scan + water | slider | fixes | trace | Approve |
                      +-----------------------------------^-----------------------------------------+
                                                          | REST + SSE (contracts/ v1.2)
+---------------------------------------------- FastAPI backend ----------------------------------------------+
|                                                                                                             |
|   deepagents orchestrator (Gemini 3.6 Flash): plan -> delegate -> memory -> re-plan -> approval             |
|     |-- site-scout ........ find_entry_points ............. Vexcel aerials + FEMA + CoStar door counts       |
|     |-- interior-surveyor . list/survey_area/relook ....... Matterport panoramas + mesh (Gemini vision)     |
|     |-- market-analyst .... get_building_value ............ CoStar assessor value, size, scan coverage      |
|     |-- scenario-builder .. run_scenario .................. loss model (value classes + Hazus 6.1 curves)   |
|     |-- mitigation-planner  rank_mitigations .............. avoided loss per dollar, re-rank on depth change|
|     `-- communications .... draft_documents ............... report + playbook (numbers guard)              |
|   send_playbook: pauses for a person (human-in-the-loop interrupt), SMTP to ALLOWED_RECIPIENTS only          |
|                                                                                                             |
|   Agent file system: /dossier/<id>/*.md|html (StateBackend)   /memories/ (SQLite StoreBackend)   /skills/   |
|   Everything external is cached in data/cache/; DEMO_MODE=1 runs from cache with the network off            |
+-------------------------------------------------------------------------------------------------------------+
        |                     |                         |                       |                  |
     CoStar               Matterport                 Vexcel             FEMA NFHL, USGS        Gemini API
  (kit JSONL)     (Model API: mesh, panoramas)   (ortho + obliques)      (public)         (vision + agent)
```

### How the three data layers combine

Each layer changes the result; take one away and a number changes or disappears.

- **Matterport → what is inside and how high.**
  - The surveyor reads every scan position's panorama with Gemini vision and finds each item's lowest vulnerable part.
  - It measures that height by casting a ray onto the scan's 3D mesh. A visual estimate is the fallback, at lower confidence.
  - Without Matterport there is no contents loss at all: the building drops to "structure only" on the triage map.
- **CoStar → what it is worth and what to expect.**
  - The assessor's improvement value, scaled by the share of the building the scan covers, is the basis for structure loss.
  - The property type picks the FEMA Hazus 6.1 depth-damage curve.
  - CoStar's drive-in and dock counts are checked against the aerial count. When they disagree, the agent reports a discrepancy and lowers its confidence. On E: 3 drive-in doors seen, 4 recorded.
- **Vexcel → where water gets in.**
  - Gemini reads the ortho and four oblique views and ranks openings: grade-level drive-in doors and personnel doors first, dock-high doors last.
  - The entry points set which fixes are offered (barriers per opening) and what they cost.
- **FEMA and USGS → where the water level sits.**
  - USGS ground elevation (3DEP, NAVD 88), sampled around the walls and in front of each door, ranks the doors by where water collects first. Plus an assumed slab allowance, it gives the floor elevation.
  - FEMA's 1% annual-chance flood level (NFHL cross-sections, NAVD 88) is placed on the same scale: "stays 1.3 ft below this floor" on E, "about 0.2 ft above it" on B.
  - The mapped flood zone labels each building.

### The loss model

- **Depth is a scenario tied to elevation, not a forecast.**
  - Waterline does not simulate rainfall, drainage or how water arrives.
  - Each slider depth is tied to real elevations: the outside water surface equals the estimated floor elevation (USGS ground plus an assumed slab allowance, ft NAVD 88) plus that depth. FEMA's 1% flood level is marked on the same scale.
  - The assumptions behind this: the slab allowance (G-SLAB-*, assumed range), the USGS ground accuracy (RMSE 0.53 m, carried into the floor range), and the datum (NAVD 88 on both sides, verified).
- **Contents damage is gradual.** Each item loses (depth − lowest vulnerable point) ÷ its class's critical height, capped at 1.
  - Values come from 15 value classes (forklift, machine tool, racked inventory, IT, and so on). Each is a team-set "assumed range, editable", shown with its id.
- **Structure loss** = the Hazus 6.1 curve × assessor improvement value × scan coverage.
- **Every dollar figure is a median with an 80% interval,** from 4,000 seeded draws (`backend/app/loss/sim.py`):
  - Each item's value is lognormal between its class's low and high (10th and 90th percentiles), and items in a class move together (correlation 0.5).
  - Each lowest vulnerable point falls anywhere in its height range.
  - Structure moves between the Hazus low and high curves.
  - The old "every item at its low end" and "every item at its high end" sums are kept only as extreme bounds in the assumptions list.
  - Every assumption id appears in the UI and the report.
- **Measured, with no dollar assumption:** how many items the water reaches at each step, and the depths where it first reaches an item, half of them, 80% of them, and the first electrical and IT item.
- **Standard method beside ours:** the Hazus 6.1 default contents and inventory curves applied to the same item values.

## How deepagents is used

`create_deep_agent` from deepagents 0.7.38 (`backend/app/agent/`):

- **Sub-agents.**
  - Six specialists, each with only its own tools, delegated through `task()`. Site, interior and market work run in parallel, then scenario and mitigations.
  - The sub-agents run on Gemini 3.5 Flash-Lite. Each one's reply is its final tool's exact output: a middleware returns it without a model call. Flash-Lite garbled numbers when it paraphrased.
- **Planning.** `write_todos` is called before acting, and again when the user moves the depth slider. Both show in the trace as a plan and a re-plan.
- **Dossier files.**
  - Each tool writes its long result to `/dossier/<id>/`: `entry-points.md`, `inventory.md`, `scenario-<d>ft.md`, `mitigations-<d>ft.md`, `report.html`, `playbook.html`.
  - Tool messages stay short. `GET /buildings/{id}/dossier` lists the files.
- **Skills.** `survey-method` and `loss-method` (SKILL.md with frontmatter) are loaded on demand by the sub-agent that needs them. The trace shows each load.
- **Memory.**
  - A person's correction (`PATCH` / `DELETE` on an asset) is saved to `/memories/` in a SQLite store.
  - On the next run the orchestrator reads it, judges each look-alike asset against the person's note, applies the correction where it fits, and says what it skipped and why.
- **Human approval.** `interrupt_on={"send_playbook": ...}` with a SQLite checkpointer. The run pauses until `POST /send` approves or rejects it. Mail goes only to `ALLOWED_RECIPIENTS`.
- **Live trace.** Every plan, delegation, tool call, decision, re-plan, file write, skill load and approval wait is an AgentEvent, streamed over SSE and saved for replay.
- **Numbers guard.** Every dollar figure the orchestrator writes, and every one in the report and playbook, must match a figure from a tool result or dossier file. An unmatched figure is removed and the removal is logged in the trace.

A full run on E reads all 49 scan positions (cached), in three batches, largest area first. Then it prices at 1 ft, re-plans at 4 ft, drafts and waits for approval. The pinned demo run took 48 s, 29 model calls and $0.13 (`docs/DEMO_FACTS.md`).

## Run it

Needs Python 3.11 or newer, Node.js with npm, the sponsor toolkit in `data/toolkit/` and keys in `.env` (copy `.env.example`; names only, no values).

```bash
# backend
cd backend
python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.sources.shortlist         # pick the shortlist -> data/cache/shortlist.json
.venv/bin/python -m app.sources.pull              # pull and cache every layer (about 2 GB)
.venv/bin/python -m app.loss.build_curves         # Hazus 6.1 structure curves -> app/loss/curves.yaml
.venv/bin/python -m app.survey.interior building-e   # vision survey (adds to the stored survey; --cached-positions-only)
.venv/bin/python -m app.survey.site building-e       # entry points from the aerial images
.venv/bin/python -m app.loss.rank                 # loss at 1, 2, 4, 6 ft for the triage map
.venv/bin/python -m app.loss.grounding            # USGS ground + FEMA 1% level per building (EPQS is slow; cached)
.venv/bin/python -m app.agent.run building-e --depth 1 --new-depth 4 --approve   # live agent run
.venv/bin/python -m app.demo reset                # demo starting state (from cache, no model calls; repeatable)
.venv/bin/python -m pytest -q

# serve the API for the front end (keep it running)
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

# front end, in another terminal
cd frontend && npm install && npm run dev        # http://localhost:3000
```

- **Demo:** `python -m app.demo reset` (or `POST /demo/reset`) restores the starting state: full stored surveys, one human correction on E, no agent session, depth 1 ft. `python -m app.demo pin building-e` pins the latest run as the demo replay.
- `DEMO_MODE=1` (in `.env` or in front of the uvicorn command) serves everything from `data/cache/` with no network except the 3D viewer.
  - `POST /run` then serves "Replay last run": the saved trace, labelled as a replay.
  - `{"live": true}` still starts a live run when the network is on.
  - `DEMO_MODE=1 .venv/bin/python -m app.sources.pull` checks that the cache is complete.
- To keep the API running after the terminal closes:

  ```bash
  nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 > ../data/cache/uvicorn.log 2>&1 &
  ```

  Stop it with `kill $(lsof -tiTCP:8000 -sTCP:LISTEN)`.
- Gemini spend is logged per call in `data/cache/spend.json`. A call that could pass `GEMINI_BUDGET_USD` is refused before it is made.

### API

All responses follow `contracts/`. CORS allows `http://localhost:3000`. The building `fixture-1` (FIXTURE, not real data) supports every endpoint.

| Endpoint | Returns |
|---|---|
| `GET /buildings` | Buildings, ranked by loss at 2 ft |
| `GET /buildings/{id}` | `{"building", "entry_points", "assets"}` |
| `GET /triage?depth_ft=1\|2\|4\|6` | Every building ranked by median total loss (with the 80% interval), with "N of M positions read" and contents count from the stored survey, labelled `surveyed` or `structure only` |
| `GET /buildings/{id}/scenario?depth_ft=` | ScenarioResult at any depth from 0 to 8 ft |
| `GET /buildings/{id}/scenario_table` | Every slider step (0 to 8 ft by 0.25 ft): median and 80% interval, items in the water, thresholds, top contributors, Hazus comparison, each asset's damage fraction and expected loss |
| `GET /buildings/{id}/grounding` | Floor elevation, the outside water surface at each slider step, FEMA's 1% level and the lowest door's ground as gauge marks (ft NAVD 88) |
| `GET /buildings/{id}/mitigations?depth_ft=` | Ranked fixes at that depth |
| `GET /buildings/{id}/media` | Mesh, aerial images, and panorama faces cleared by the privacy screen |
| `PATCH` / `DELETE /buildings/{id}/assets/{asset_id}` | Human correction or removal: saved, applied on every read, written to the agent's memory |
| `POST /buildings/{id}/run` | Starts the live agent (`{"depth_ft": 1}`). `{"replay": true}`, or demo mode, gives the last saved run (in demo mode the pinned hero run), labelled REPLAY |
| `POST /buildings/{id}/depth` | `{"depth_ft": 4}`: the agent re-plans, re-prices and re-ranks |
| `POST /buildings/{id}/request_send` | The agent drafts the documents and calls `send_playbook`, which waits for approval |
| `POST /buildings/{id}/send` | `{"approved": true, "recipient": "..."}` resumes the waiting agent (`false` rejects). Sends over SMTP when `SMTP_*` and `EMAIL_FROM` are set; otherwise `draft_only` |
| `GET /buildings/{id}/events?speed=&replay=&after=` | SSE AgentEvents: live while the agent runs (`after` or the `Last-Event-ID` header skips events already seen), otherwise the last saved run, which opens with a `replay` event carrying the label |
| `GET /buildings/{id}/agent`, `/runs/latest`, `/dossier` | Session status; the last saved run's label and stats; the agent's files |
| `POST /demo/reset`, `GET /demo/state` | Demo starting state: full stored surveys, one human correction on E, no agent session, depth 1 ft (localhost only; from cache) |
| `GET /buildings/{id}/report?depth_ft=`, `/playbook?depth_ft=` | HTML |
| `GET /media/{id}/...` | Cached meshes, panoramas and aerial images (localhost only; only faces the privacy screen cleared) |

## Limitations

- **Scanned area only.** Contents loss counts only items visible from the scan positions read. Structure loss is scaled to the scanned share of the building (`scan_coverage`).
  - B, D, E and G are fully surveyed (11 of 11, 33 of 33, 49 of 49 and 27 of 27 positions). A, C, F and H read 13 to 15 positions each, so their contents loss is a floor, not an estimate of the whole building.
  - Every building shows "N of M positions read".
- **Value ranges are assumptions.** All 15 value classes and all 5 mitigation costs are team-set, shown as "assumed range, editable" with their id. A person can correct any asset's value or height, and the correction is remembered.
- **Comparison with Hazus.** The FEMA Hazus 6.1 default contents and inventory curves (COM2), applied to the same item values, are shown beside ours and are not used in the numbers.
  - On E and B, our median contents loss is higher: 1.5 to 2.3 times the Hazus-style figure at 1 to 6 ft.
  - The shapes differ:
    - Hazus applies a building-average percentage from the first inch of water (16% of contents at 1 ft) and never reaches 100% (72% at 8 ft), because a building's contents include things stored above the water.
    - Waterline prices only the items the survey saw, from each item's own height. On E, 89% of the surveyed value sits in items whose lowest vulnerable part may be below 1 ft.
- **The interval is about the stated uncertainty only.** It reflects the value ranges, the height ranges and the Hazus structure range. Items the survey missed and a class range that is wrong for a whole building beyond the shared class factor are not in it.
- **A partial "quick scan" was no better than random** (development option only): on E, 12 positions split by area size found 28–34% of the full survey's contents value; random sets of 12 averaged 27–31%. Every building's survey therefore reads every position it covers.
- **Heights.** Heights come from the mesh where it resolves the item; otherwise they are a wider visual estimate at lower confidence. Items cut off by the image edge, small or far away get lower confidence. Some low-confidence items (for example boom lifts on E) are not visible from any neighbouring position, so a re-look cannot confirm them.
- **Entry points** are seen from the air. Door threshold heights are not measured: the ground in front of each door is, and the floor is that ground plus an assumed slab allowance.
- **Elevations.** USGS ground has a stated RMSE of 0.53 m (1.74 ft), which is carried into the floor range, so FEMA's level can fall either side of the floor on E and B. The FEMA level for a building outside the zone is the nearest mapped one, a reference only. No Harvey high-water marks are used: FEMA's layer has none within 8 km, and the USGS service could not be verified in time.
- **The depth is a scenario.** Waterline does not forecast floods or model rainfall, drainage, flow, or how water spreads between rooms.
- **Email** goes out only when SMTP settings are configured. Without them an approved send is recorded as "draft only, not sent".

## Data and secrets

- `.env`, `data/toolkit/` and `data/cache/` are git-ignored.
- CoStar, Matterport and Vexcel data are proprietary and never committed. Buildings appear by letter only, and CoStar property ids stay server-side.
- Keys are sent in headers, never in URLs or logs. The Matterport token is used read-only and server-side only.
- Panorama faces showing identifiable people, children's spaces or personal documents are never served.
