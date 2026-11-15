# Audit: every number and claim, with its source

Checked 2026-11-14 against the code on `main`. "Source" names a data field or a computation over sourced data. "Assumption" names an id in `backend/app/loss/assumptions.yaml` or `curves.yaml`; the UI and report show these ids. **FLAG** marks a number or claim with neither: it is a method constant chosen by the team, set in code. Flags are listed together in section 6, and every team-set assumption (`placeholder: true`) still in use is listed in section 7.

Buildings are named by letter. Real values live only in the git-ignored cache.

## 1. Building (`GET /buildings`, `GET /buildings/{id}`)

Each field's source is written in its schema description, `contracts/building.schema.json`.

| Field | Source |
|---|---|
| `lat`, `lng`, `size_sqft`, `year_built`, `stories`, `property_type`, `property_subtype`, `tenants` | CoStar property record |
| `value_usd`, `improvement_value_usd`, `value_as_of`, `value_source` | Assessor values from the latest CoStar sale comp. Only `improvement_value_usd` is used in a number (S-VALUE-BASIS). |
| `loading_docks_external`, `drive_in_bays` | CoStar industrial, flex or retail record |
| `scan_area_sqft` | Matterport `model.dimensions.areaFloor` |
| `scan_coverage` | `min(scan_area_sqft / size_sqft, 1)`, a computation. The cap is in the schema description. |
| `flood_zone`, `flood_zone_subtype`, `in_mapped_flood_zone`, `flood_zone_source` | FEMA NFHL `FLD_ZONE` at the building point |
| `ground_elevation_ft` | USGS EPQS at the CoStar point, ft NAVD 88 (datum confirmed from USGS 3DEP documentation, v1.3). The sampled ground is in `/grounding` (section 4b). |
| `aerial_collection`, `aerial_capture_date` | Vexcel ortho image metadata |

## 2. Entry points (`GET /buildings/{id}`, `entry_points`)

| Number or claim | Source or assumption |
|---|---|
| Kind, image box, evidence text | Gemini reading of the Vexcel ortho and oblique views (`survey/site.py`); the prompt and model are logged in `site_log.json` |
| `lat`, `lng` | Ortho pixel converted with the Vexcel image's georeference (computation) |
| `threshold_elevation_ft` | Always null. Never invented (AGENTS.md section 5 rule 1). |
| `confidence` | Gemini's own score. **FLAG:** multiplied by 0.8 (`DISCREPANCY_FACTOR`) when the aerial count of that kind of door differs from CoStar's. |
| Rank order (drive-in, door, garage, ramp, other, dock) | **FLAG:** method order (`KIND_ORDER`): grade-level openings first |
| "Layer discrepancy: N seen, M recorded" | Vexcel count (Gemini) against CoStar `drive_in_bays` / `loading_docks_external` |

## 3. Assets (`GET /buildings/{id}`, `assets`; `/scenario_table` `assets`)

| Number or claim | Source or assumption |
|---|---|
| Label, category, room type, evidence | Gemini reading of Matterport panorama faces (prompt in `survey/interior.py`; model per observation) |
| `height_ft_low` / `height_ft_high` "measured from mesh" | Ray cast from the panorama pixel onto the Matterport mesh (`survey/geometry.py`, verified convention in DATA_NOTES section 12). **FLAG:** plus or minus 0.15 ft geometry tolerance (`MESH_TOL_FT`). |
| Heights "estimated" | Gemini visual estimate, kept as a wider range when the mesh disagrees or misses |
| `confidence` | Gemini's own score. **FLAG:** × 0.85 for each small box (under 2,500 in 1000² units), far item (over 10 m) or box cut by a side or top edge; a box cut by the bottom of the image assumes the floor and is capped at 0.55. |
| "Below confidence 0.6", re-look trigger | **FLAG:** `LOW_CONF = 0.6` |
| One asset per object | **FLAG:** sightings merge within 0.5 m with the same class, or within 1.5 m when the labels share a specific noun. This sets the asset count and so the contents loss. |
| `value_basis` | Keyword rules over the label (`loss/classes.py`); **FLAG** for the rules themselves. The class values are assumptions below. |
| `value_usd_low` / `value_usd_high` | V-* value class (assumed range, editable; section 7), or a human correction (`corrections.json`, id `corr-*`) |
| `room` | Matterport room label, else the room type Gemini saw most there; duplicates are numbered ("Office 2") |
| `position` | Mesh ray cast of the box centre |
| "N of M positions read" | The stored survey (`survey_log.json`): the same count everywhere (section 5) |

## 4. Loss (`/scenario`, `/scenario_table`, `/triage`, `/mitigations`)

| Number or claim | Source or assumption |
|---|---|
| Depth | Chosen by the user: a scenario, not a forecast |
| `likely` / `possible` | Method in AGENTS.md section 9: likely when depth ≥ `height_ft_high`, possible when depth ≥ `height_ft_low` |
| Contents loss median, low (p10), high (p90) | C-CONTENTS-DEPTH over each asset's value class (V-* values and `critical_ft`), simulated: C-MC-VALUE (lognormal, class low/high as p10/p90), C-MC-CLASS-CORR (0.5, team-set), C-MC-HEIGHT, C-MC-DRAWS (4,000 draws, seed 20261114). **FLAG:** the critical height is never below 0.25 ft (`MIN_CRITICAL_FT`); this floor is not in the assumption text. **FLAG:** simulated figures are rounded to 3 significant figures (`sim.sig`). **FLAG:** percentiles are clamped inside the extreme bounds (`sim._clamp`; tested to move them by under 3%). |
| Extreme bounds | X-EXTREME-BOUNDS: the pre-v1.3 sums (low value + top of height range; high value + bottom), listed in the assumptions only |
| Items in the water, thresholds | Item heights only (`sim.in_water`, `sim.thresholds`), no dollar figure; mesh-measured or estimated per item (count shown) |
| Top contributors, expected loss per asset | Mean of the simulated draws per asset |
| Standard-method comparison | Hazus 6.1 default contents (COM1 90, COM2 195, IND2 384) and inventory (1, 46, 81) functions (`curves.yaml` `standard_contents`, cited) on the same simulated values. **FLAG:** "about the same" means within 0.8–1.25 times (`sim.SAME_BAND`). |
| Item height used to cap the critical height | Mesh span above the lowest point (`asset_geometry.json`) |
| Vehicles excluded from contents loss | V-VEHICLE (human decision) |
| Fabric at $0 | A-FIN (Waterline method: the structure curve already prices it) |
| Structure loss median, low (p10), high (p90) | Simulated between the Hazus low and high curves (C-MC-STRUCT). Hazus 6.1 structure curve C-HAZUS-COM1 / COM2 / IND2 (`curves.yaml`, cited to FEMA Hazus 6.1 via NHERI SimCenter), interpolated at the depth, times S-VALUE-BASIS (assessor improvement value × scan coverage) |
| `scenario_table` rows | The same function at 0 to 8 ft in 0.25 ft steps; each row equals `/scenario` at that depth (tested) |
| Triage `total`, `total_median` | Simulated contents plus structure at 1, 2, 4 and 6 ft. The ranking order (median at the chosen depth) is a method. |
| Triage `status` "surveyed" / "structure only" | Whether a stored survey exists |
| Mitigation `cost_usd_*` | M-PLATFORM, M-ELEC-RAISE, M-MOVE-INV, M-MOVE-VEHICLES, M-BARRIER × count of items, rooms, openings or vehicles |
| Mitigation `avoided_loss_usd_*` (median, p10, p90) | Contents and structure loss before and after the action, on the same simulated draws. Raise heights, target heights and barrier rating come from the M-* entries. |
| Mitigation rank; payback note "about X times its cost in one event" | **FLAG:** method: ratio of the median avoided loss to the cost midpoint; actions that avoid nothing rank last |
| "Drive vehicles to high ground": avoided loss $0 | By design: vehicle value is not priced (M-MOVE-VEHICLES note) |

## 4b. Elevation grounding (`GET /buildings/{id}/grounding`, contracts v1.3)

| Number or claim | Source or assumption |
|---|---|
| Ground elevations (adjacent, around, at each door) | USGS EPQS (3DEP), ft NAVD 88, RMSE 0.53 m (G-GROUND, USGS FAQ). **FLAG:** sample layout: 3 m outside the walls, about 12 points; a 3 × 3 grid out to 40 m; 2 m in front of each door (`grounding.RING_*`, `GRID_*`, `DOOR_OFFSET_M`). |
| Door ranking, "water collects there first", lead in ft | Ground in front of each mapped door (computation). "About level" below 0.5 ft: G-LEVEL-TOL (team-set). |
| Floor elevation | Ground at the governing doors + slab allowance G-SLAB-GRADE / G-SLAB-DOCK / G-SLAB-STEP (team-set, "assumed range, editable"), chosen from CoStar door counts and the doors mapped from the aerial images. The range adds 1 RMSE of the ground. |
| FEMA 1% flood level | NFHL layer 14 `WSEL_REG` (two nearest cross-sections on the nearest flooding source, inverse-distance weighted; range between them), with layer 16 `ELEV` as a check; `V_DATUM` and distance reported (G-FEMA-1PCT). **FLAG:** search radius 3 km, then 8 km. |
| FEMA level relative to the floor | FEMA level − floor, with the range from both ranges. The building outside the zone gets the nearest level and the sentence "a reference, not a claim that it applies here". |
| Outside water surface per slider step | Floor + depth (G-WSE: water inside rises to the outside level; no rainfall, drainage or flow model) |
| Datum statement | USGS FAQ (EPQS from 3DEP) + USGS 3DEP DEM metadata (NAVD 88) + FEMA `V_DATUM` NAVD88 (G-DATUM) |

## 5. Agent, report, playbook, send

| Number or claim | Source or assumption |
|---|---|
| AgentEvent text from tools (site, survey, re-look, scenario, ranking, priority changes, memory) | Written by the tools from the results above; every event is validated against the contract |
| Orchestrator messages | Written by the model. **Numbers guard:** every dollar figure must match a tool result or dossier file, otherwise it is replaced by "[figure removed]" and an observation event is logged (`agent/guard.py`, tested). |
| "N of M positions read", contents count, contents value in agent messages | `finish_survey` / `survey_area` on the stored survey: the same numbers as `/triage` and the report |
| "Priority change … rank a → b (avoided loss … → …)" | `rank_mitigations` with the previous depth (computation) |
| Applied a human correction to similar assets | `corrections.json` (`by: "agent"`, `propagated_from`), with the agent's reason |
| Run time, model calls, tokens, cost (`/agent`, runs files) | LangChain usage metadata × `PRICES_PER_M` (aistudio.google.com/docs/pricing, Standard tier, checked 2026-11-14) |
| Replay label "REPLAY of the last saved run (id, recorded at)" | The saved trace's first event time and file name |
| Report: building facts, FEMA zone | Section 1 |
| Report: total, contents and structure loss (median and 80% interval), measured counts and thresholds, top contributors, Hazus comparison, elevation section, assets table with expected loss, mitigations table, assumptions list (with X-EXTREME-BOUNDS and G-*), each team-set one marked "assumed range, editable" | Sections 3, 4 and 4b. Every dollar figure passes the numbers guard (tested for every building at 1 and 4 ft). |
| Report: "the 3D scan covers X sq ft, Y% of the building" | `scan_area_sqft`, `scan_coverage` |
| Report and playbook: "Interior survey read N of M scan positions; K contents assets" | Stored survey (`rank.survey_status`) |
| Playbook steps and "avoids $a-b" | Ranked mitigations at the depth |
| Playbook room order | **FLAG:** method: by the high end of the avoided loss of the room's actions |
| Playbook title "Pre-storm playbook" | Renamed from "72-hour pre-storm playbook" (human decision 2026-11-14): the steps carry no times, so no timeline is claimed |
| Send status `sent` / `draft_only` / `refused` / `failed` | `actions/send.py`: approval, `ALLOWED_RECIPIENTS`, SMTP settings, `DEMO_MODE` |
| Media manifest: which panorama faces are shown | Gemini privacy screen per face (identifiable people, children's spaces, personal documents); unscreened faces are never served |

## 6. Flags: numbers and claims with no source and no assumption id

These are team method choices set in code. Each changes a number shown, so each should get an assumption id (or be noted in the UI) if time allows. Item 11 is resolved.

1. Entry point confidence × 0.8 on a CoStar count mismatch (`survey/site.py` `DISCREPANCY_FACTOR`).
2. Entry point rank order by kind (`KIND_ORDER`).
3. Asset confidence penalties: × 0.85 for small, far or edge-cut boxes (thresholds 2,500, 10 m, 10/1000), and the bottom-edge rule (confidence × 0.6, at most 0.55) (`survey/interior.py`).
4. Mesh agreement tolerance of 0.15 ft (`MESH_TOL_FT`).
5. Low-confidence threshold 0.6 (`LOW_CONF`), used for re-looks and the "below 0.6" counts.
6. Merge distances of 0.5 m and 1.5 m (`MERGE_M`, `NOUN_MERGE_M`). They set the asset count.
7. Keyword rules that assign a value class from the label (`loss/classes.py`).
8. Minimum critical height of 0.25 ft (`MIN_CRITICAL_FT`), not stated in C-CONTENTS-DEPTH.
9. Mitigation ranking and the payback ratio (midpoint ÷ midpoint).
10. Playbook room order.
11. ~~Playbook title "72-hour"~~: resolved, renamed "Pre-storm playbook".
12. 3-significant-figure rounding of simulated figures, and the clamp of percentiles inside the extreme bounds (`sim.py`).
13. "About the same" band for the Hazus comparison: 0.8–1.25 times (`sim.SAME_BAND`).
14. Grounding sample layout and FEMA search radius (`grounding.py`).

No dollar figure in an API response, the report or the playbook lacks a source or assumption id: each traces to a value class, a mitigation cost, a Hazus curve × CoStar assessor value, or a human correction.

## 7. Team-set assumptions in use ("assumed range, editable")

Each keeps `placeholder: true` in `assumptions.yaml` and in the scenario `assumptions` list, so the UI can badge it. The API source text, the report and the documents call it "assumed range, editable" with its id.

- **Value classes (all 15 in use across the eight buildings):** V-FORKLIFT, V-AERIAL-LIFT, V-PALLET-JACK, V-MACHINE-TOOL, V-SHOP-EQUIP, V-HAND-TOOLS, V-RACKED-INV, V-FLOOR-INV, V-OFFICE-FURN, V-APPLIANCE, V-IT, V-ELEC-GEAR, V-HVAC, V-SMALL, V-OTHER. Each is a team-assumed replacement range and critical height.
- **Mitigation costs (all 5 in use):** M-PLATFORM, M-ELEC-RAISE, M-MOVE-INV, M-MOVE-VEHICLES, M-BARRIER.
- **Simulation (v1.3):** C-MC-CLASS-CORR (correlation 0.5 between log-values within a value class).
- **Elevation (v1.3):** G-SLAB-GRADE, G-SLAB-DOCK, G-SLAB-STEP (slab allowances), G-LEVEL-TOL (0.5 ft).
- **Not placeholders:** S-VALUE-BASIS (CoStar assessor value), C-CONTENTS-DEPTH (method), C-HAZUS-* (FEMA Hazus 6.1), V-VEHICLE (human decision), A-FIN (method), C-MC-VALUE / C-MC-HEIGHT / C-MC-STRUCT / C-MC-DRAWS (simulation method), X-EXTREME-BOUNDS (method), G-GROUND / G-FEMA-1PCT / G-DATUM (sourced), G-WSE (method).
- **The `fixture-1` building** and everything in `contracts/fixtures/` are FIXTURE data, labelled as such in every response.
