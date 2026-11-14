# Waterline: standing brief for coding agents

Save this file in the repo root as both `AGENTS.md` (Codex) and `CLAUDE.md` (Claude Code).
Read it fully before every task. The step-by-step prompts live in `BUILD_PROMPTS.md`.

## 1. What we are building

Waterline is an AI agent for the HackPrinceton Fall 2026 CoStar track.
Given a commercial building in Houston, it:

1. Finds where flood water gets in, from Vexcel aerial imagery and ground elevation.
2. Walks the building's Matterport 3D scan and inventories what a flood would damage, with a height estimate for each asset.
3. Prices the loss for a chosen water depth, using CoStar building data.
4. Shows water rising inside the 3D model while a dollar counter climbs.
5. Ranks fixes by payback, writes a resilience report and a room-by-room pre-storm playbook, and sends the playbook after a human approves.

One-liner: "Flood maps stop at the front door. Waterline takes the water inside."

## 2. Deadline and priority

- Submission deadline: `sunday morning 7`. Code freeze is 2 hours before that.
- This is a hackathon. The 3-minute demo in section 4 is the product. Anything not on the demo path is optional.
- When two options exist, choose the one that makes the demo path work soonest.

## 3. How judges score (optimise for this)

| Prize | Criteria |
|---|---|
| CoStar | 30% use of data (combine at least two of CoStar, Matterport, Vexcel, intelligently); 30% agentic depth (reasons, plans, acts; not a chat wrapper); 25% usefulness (would someone switch it on Monday); 15% demo and polish |
| Amazon Practical AI | 25% each: creativity, usefulness, technical implementation, user experience. Focus areas: agentic behaviour, real-world impact, adaptive intelligence (learns from context, feedback or preferences), user-friendly design, creative innovation. Requires working prototype, clear use case and target user, basic documentation, pitch |
| LangChain | Best use of the `deepagents` library |
| Main rubric | Creativity, utility, charity, avidity |

Consequences for the build:
- All three data layers must visibly change the result. If removing a layer would not change the output, the layer is decoration.
- The agent's plan, decisions and re-plans must be visible in the UI, live.

## 4. The demo path (must work end to end, live and from cache)

1. Houston map with 6 to 8 buildings ranked by estimated interior loss. One of them sits outside the mapped flood zone.
2. Click that building. Aerial view with the agent's marked entry points (lowest door, dock ramp).
3. Interior 3D scan with the agent's tagged assets.
4. Drag the water-depth slider. Water rises, hit assets turn red, the loss range updates.
5. Ranked mitigations with cost, avoided loss and payback.
6. Drafted report and pre-storm playbook. Human clicks Approve. It sends.
7. The agent trace panel shows plan, tool calls, decisions and one re-plan throughout.

## 5. Hard rules

1. **Never invent data, fields, endpoints or SDK methods.** Nobody on the team has verified the CoStar hackathon toolkit. Read the toolkit docs and call the real APIs before writing code against them. Record what you find in `docs/DATA_NOTES.md`. If something is missing, say so and stop; do not fake it.
2. **Secrets.** Keys live only in `.env`, which is git-ignored. Keep `.env.example` current with names and no values. Never print, log, commit or paste a key. Never put a key in front-end code unless the vendor's docs say that key is meant to be public. The Matterport API token pair (`MATTERPORT_API_KEY`, `MATTERPORT_API_TOKEN`) has admin rights over the account: use it server-side only and for read-only queries only. The backend client refuses any GraphQL mutation. Only `NEXT_PUBLIC_MATTERPORT_SDK_KEY` may reach the front end.
3. **Sponsor data.** The repo will be public. Treat CoStar, Matterport and Vexcel data as proprietary: `data/cache/` is git-ignored and raw sponsor data is never committed, unless a human tells you the sponsor approved it.
4. **Cache everything.** Every external call writes its response to `data/cache/`. `DEMO_MODE=1` must run the full demo path from cache with no network except the 3D viewer.
5. **Honest numbers.** Every dollar figure is a low-high range. Every asset height has a confidence. Water depths are scenarios chosen by the user, not predictions. Every assumption used in a number is listed in the UI and the report. Placeholder values are labelled `PLACEHOLDER` in data and in the UI.
6. **Human in the loop.** Nothing is sent without an explicit Approve click. Sends go only to addresses in `ALLOWED_RECIPIENTS`.
7. **Stay in your lane.** Each workstream owns its directories (section 7). Change `contracts/` only when the human says both agents have been told.
8. **Stop at checkpoints.** Each prompt in `BUILD_PROMPTS.md` ends with a checkpoint. Stop there, report what works, what does not, and what you assumed. Do not start the next phase unprompted.
9. **No extras.** No auth, no user accounts, no database migrations framework, no CI, no Docker unless asked. Small commits with clear messages.
10. **Verify, then claim.** Run the code before saying it works. Say plainly when something is untested.

## 6. Architecture

```
waterline/
  AGENTS.md  CLAUDE.md  BUILD_PROMPTS.md  README.md
  .env.example  .gitignore
  contracts/          JSON Schemas + fixtures (shared, frozen after Phase 1)
  docs/               DATA_NOTES.md, DECISIONS.md
  backend/            Python 3.11+, FastAPI
    app/main.py       REST + SSE
    app/sources/      costar.py, matterport.py, vexcel.py, elevation.py (thin clients + cache)
    app/survey/       interior.py (vision inventory), site.py (entry points)
    app/loss/         model.py, assumptions.yaml, curves.yaml
    app/agent/        orchestrator.py, subagents.py, tools.py, events.py
    app/actions/      report.py, playbook.py, send.py
    tests/
  frontend/           Next.js (App Router, TypeScript)
    app/              / (triage map), /building/[id]
    components/       Map, AerialPanel, Viewer3D, WaterSlider, LossCounter, AssetList,
                      MitigationTable, AgentTrace, ApprovePanel
  data/toolkit/       sponsor kit: costar-hackathon-kit/, vexcel/ (git-ignored, proprietary)
  data/cache/         git-ignored
  data/demo/          derived, non-proprietary demo outputs only
```

The sponsor toolkit lives in `data/toolkit/`, not `docs/toolkit/`. What it contains and how each source behaves is in `docs/DATA_NOTES.md`.

Stack: FastAPI, `deepagents` for orchestration, a Gemini vision model for panorama reading (model name from `GEMINI_MODEL`), MongoDB Atlas only if time allows (JSON files on disk are the default store), Next.js front end.

## 7. Workstreams

| Workstream | Tool | Owns |
|---|---|---|
| A: data, survey, loss, agent | Claude Code | `backend/`, `docs/` |
| B: UI, map, 3D viewer, slider | Codex | `frontend/` |
| Shared | Human decides | `contracts/`, root files |

Both tools work on `main` in the same folder. Claude Code commits only `backend/`, `contracts/`, `docs/` and root files; Codex commits only `frontend/`. Always stage with `git add <your paths>`, never `git add -A`. Workstream B builds against `contracts/fixtures/` until the real API is ready, so it is never blocked.

## 8. Contracts (frozen)

**`contracts/` v1.1.0 is the source of truth.** Read `contracts/README.md` for the schemas (Building, EntryPoint, Asset, ScenarioResult, Mitigation, AgentEvent), the fixtures, and the changelog.

v1.1.0 changed three things:
- Building ids are slugs such as `building-h`. They appear in URLs and as `building_id` everywhere.
- No CoStar property id appears in any response, URL, UI or committed file.
- `Building.scan_coverage` is new: scanned area ÷ CoStar GBA, capped at 1.

Each schema property's description names the source field it maps from. Change `contracts/` only under rule 7 of section 5.

API (backend):
- `GET /buildings` list of Building for the triage map
- `GET /buildings/{id}` `{"building": Building, "entry_points": [EntryPoint], "assets": [Asset]}`
- `GET /buildings/{id}/media` media manifest (mesh, aerial images, panorama faces cleared by the privacy screen)
- `GET /media/{path}` cached meshes, panoramas and aerial images (served to localhost only)
- `GET /buildings/{id}/scenario?depth_ft=` ScenarioResult (must answer in under 100 ms: pure computation over cached assets, so the slider is smooth; the front end may also compute client-side from the same data)
- `GET /buildings/{id}/mitigations?depth_ft=`
- `POST /buildings/{id}/run` starts the agent; `GET /buildings/{id}/events` SSE stream of AgentEvent
- `GET /buildings/{id}/report`, `GET /buildings/{id}/playbook`
- `POST /buildings/{id}/send` requires `{"approved": true}`

## 9. Loss model (keep it simple and defensible)

- The slider sets **interior water depth above the ground-floor slab**, 0 to 8 ft. Entry points explain where water enters first; they do not need to drive a hydraulic model.
- An asset is **likely** hit when `depth >= height_ft_high`, **possible** when `depth >= height_ft_low`.
- `loss_low` = sum of `value_usd_low` over likely assets. `loss_high` = sum of `value_usd_high` over likely and possible assets.
- Structure and finishes loss comes from a depth-damage curve per property type in `curves.yaml`, applied to a value basis from CoStar data. Source the curves from FEMA Hazus documentation if you can retrieve and cite them. If you cannot, write a clearly labelled placeholder curve, set `placeholder: true`, and show that label in the UI. Never present a placeholder as a FEMA figure.
- Asset replacement values come from `assumptions.yaml`: a small table of low-high ranges by asset category. These are assumptions, each with an id, shown in the UI.
- Unit-test the model: zero depth gives zero loss; loss never decreases as depth rises; low is never above high.

## 10. Agent design (deepagents)

- One orchestrator built with `create_deep_agent`, plus six subagents: site-scout, interior-surveyor, market-analyst, scenario-builder, mitigation-planner, communications.
- Known shape (verify against the installed version, the API has changed between releases):
  `create_deep_agent(model=..., tools=[...], system_prompt="...", subagents=[{"name": ..., "description": ..., "system_prompt": ..., "tools": [...]}])`. Older releases used `prompt` or `instructions` instead of `system_prompt`. In recent releases the planning tool (`write_todos`) is opt-in through middleware. Read the docs for the version you install and pin that version.
- Use the agent's file system for a per-building dossier (`/dossier/{building_id}/…`): survey notes, assets, scenarios, report drafts.
- Use the library's human-in-the-loop interrupt for the send step if available; otherwise gate in our own API.
- Every plan, tool call, decision and re-plan is emitted as an AgentEvent.
- Required visible behaviours, because judges score agentic depth:
  1. Writes a survey plan before acting.
  2. Chooses which scan positions to inspect instead of reading all of them blindly, and says why.
  3. When an asset's confidence is low, looks again from a neighbouring scan position and updates the record.
  4. Re-plans once when the scenario changes (for example the user raises the depth from 1 ft to 4 ft and the priority list changes).
  5. Stops and waits for approval before sending.
  6. Adapts to feedback (Amazon's "adaptive intelligence"): when a human corrects an asset height or deletes a wrong asset, the correction is saved to the dossier, the agent re-runs the scenario and mitigation ranking, and it applies the same correction to similar assets in that building, emitting a decision event that says so.
- If the sponsor toolkit ships MCP servers, connect them as tools rather than rewriting clients.
- **How LangChain judges:** complexity of the use case, effective use of Deep Agents (sub-agents, the file system and the other harness features) and the demo.
- **Docs:** use the `docs-langchain` MCP server (`https://docs.langchain.com/mcp`) for every deepagents question.
- **Before writing agent code,** read `../hack-princeton-intro-to-deep-agents` (`modules/01`, `modules/02` and `agent.py`). Follow its patterns for streaming the live plan, files and sub-agent activity, and for approvals.
- **Harness features to use:** sub-agents, the file dossier, planning, human-in-the-loop approval, skills (survey method, loss method), and memory for human corrections.
- **Model:** vision and the orchestrator both run on Gemini. `AGENT_MODEL` uses the `provider:model` format, currently `google_genai:gemini-3.6-flash` (3.8 never answered on 2026-11-14; see docs/DECISIONS.md D7). The `langchain-google-genai` integration reads `GOOGLE_API_KEY` by default, so pass `GEMINI_API_KEY` to it explicitly. Anthropic is optional.

## 11. 3D water view: fallback ladder

Decided after Phase 0 (see `docs/DECISIONS.md`).

- **Option B (main 3D view):** our own three.js scene on the Matterport mesh. The Model API returns an OBJ mesh for almost every candidate model; the backend downloads it and serves it from `/media/`. The mesh is z-up with the floor near z = 0 and units consistent with metres, so the water plane sits at `depth_ft × 0.3048`.
- **Option C (safety net, build it first):** 2D floor plan or room list where rooms fill blue with depth and assets turn red, next to the standard embedded viewer.
- **Option A (optional extra):** Matterport Bundle SDK. The `Scene` namespace exists only in Bundle distributions and exposes the viewer's three.js as `sdk.Scene.THREE`. Try it only if time allows, and only after confirming the SDK key allows Bundle use on the front end's localhost port.

## 12. Known facts versus assumptions

Verified from public docs: the deepagents call shape above; the Matterport `Scene` namespace is Bundle-only; USGS elevation is available at
`https://epqs.nationalmap.gov/v1/json?x=<lng>&y=<lat>&wkid=4326&units=Feet&includeDate=false` and returns the elevation in `value`.

Not verified, settle in Phase 0: what the CoStar toolkit exposes; whether ground-floor scans exist for Houston; whether panoramas, room dimensions, mesh or depth are available; whether the SDK key allows Bundle; Vexcel resolution and any elevation product; flood-zone data access.

If ground-floor scans are too few, switch the hazard to water from above (roof ponding or damage seen in aerial imagery, matched to top-floor assets). The pipeline, contracts and demo stay the same.
