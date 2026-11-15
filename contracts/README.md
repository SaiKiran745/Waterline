# Contracts

**FROZEN: version 1.3.0, 2026-11-14.** Change these files only when a human says both agents (Claude Code on `backend/`, Codex on `frontend/`) have been told.

This folder is the source of truth for data shapes. Where it differs from the sketch in AGENTS.md section 8, this folder wins.

| Schema | Fixture | One record is |
|---|---|---|
| `building.schema.json` | `fixtures/building.json` | One building, from CoStar, Matterport, FEMA, USGS and Vexcel |
| `entry_point.schema.json` | `fixtures/entry_points.json` | A place water gets in, marked on a Vexcel image |
| `asset.schema.json` | `fixtures/assets.json` | A flood-vulnerable item seen in a Matterport panorama |
| `scenario_result.schema.json` | `fixtures/scenario_2ft.json`, `fixtures/scenarios.json` (0, 1, 2, 4, 8 ft) | The loss at one user-chosen depth |
| `mitigation.schema.json` | `fixtures/mitigations.json` (5 fixes, each at 1, 2 and 4 ft) | One ranked fix |
| `agent_event.schema.json` | `fixtures/agent_events.json` | One agent step on the SSE stream |
| `scenario_table.schema.json` | `fixtures/scenario_table.json` | Every slider step (0 to 8 ft by 0.25 ft) for one building, with each asset's damage fraction per step |
| `triage.schema.json` | `fixtures/triage.json` | The triage ranking: every building, labelled `surveyed` or `structure only` |
| `grounding.schema.json` | `fixtures/grounding.json` | v1.3: one building's floor elevation, the outside water surface at each slider step, and reference levels (FEMA 1% flood level, lowest door ground), ft NAVD 88 |

All schemas are JSON Schema draft 2020-12 with `additionalProperties: false`. Every field is required; unknown values are `null`, never omitted. Each schema property's `description` names the source field it comes from.

Fixtures are fake ("FIXTURE, not real data") and contain no sponsor data. Phase 1 expanded them without changing any schema:
- 25 assets in 5 rooms
- 3 entry points
- scenarios at 0, 1, 2, 4 and 8 ft, computed with the AGENTS.md section 9 rule (depth 0 hits nothing)
- 5 mitigations, each evaluated at 1, 2 and 4 ft, so the ranking changes between 1 ft and 4 ft
- a 40-event agent trace with a plan, a scan-position choice, a low-confidence re-look, a re-plan and an approval wait

`backend/tests/test_contracts.py` validates every fixture.

## Agent flow (API)

The agent runs one session per building, as up to four turns: assess → depth change → draft and request send → approval. Each turn runs in the background. A POST starts a turn and returns at once with the session status; `GET /events` streams the turn, and `GET /agent` says when it has finished. These endpoints are not JSON-schema'd. Shapes below are as implemented and tested (`backend/tests/test_api.py`, `test_demo_mode.py`).

**Typical sequence:**
1. `POST /run` and open `/events`.
2. When the stream sends `end`, `POST /depth` and reopen `/events?after=<last id>`.
3. `POST /request_send` and reopen `/events?after=…`. The stream's `end` carries `waiting_for_approval: true`.
4. `POST /send {"approved": true}` and reopen `/events?after=…`.

Unknown building: 404. Another turn still running: 409.

### `POST /buildings/{id}/run`
- **Body:** `{"depth_ft": 1}` starts a live session (turn 1, assess at that depth).
  - `{"replay": true}` returns the last saved run instead, without starting anything.
  - Under `DEMO_MODE=1`, every `/run` is a replay unless the body has `"live": true`. The demo-mode replay is the pinned hero run. It also puts that run's resulting corrections in place, so the numbers the UI fetches match the ones the trace quotes; `POST /demo/reset` restores the starting state.
- **Live response:** the session status (see `GET /agent`).
- **Replay response:** `{"status": "replay", "building_id", "run_id", "recorded_at", "events", "seconds", "cost_usd", "model_calls", "turns", "replay": true, "label", "events_url"}`, plus `"outcome_applied"` in demo mode.
  - `label` starts with `REPLAY` and must be shown while it plays.
  - `events_url` is `/buildings/{id}/events?replay=1`.
- **Errors:** 404 when there is no saved run to replay; 409 when a turn is still running.

### `GET /buildings/{id}/events` (Server-Sent Events)
- **Query:**
  - `after=<event id>`: send only events with a larger id. A reconnecting `EventSource` sends `Last-Event-ID`, which is honoured the same way.
  - `replay=1`: force the saved run even while a session exists.
  - `speed=1`: replay pacing; 0 sends everything at once.
- **Live** (a session exists):
  - `event: agent_event` with `id: <event id>` and `data: AgentEvent` (`agent_event.schema.json`), for every event after `after`. New ones follow as they arrive.
  - When the current turn ends: `event: end`, `data: {"events", "waiting_for_approval", "error"}`. The stream then closes.
  - Without `after`, each connection resends the session from its first event.
- **Replay** (no session, or `replay=1`): `event: replay` first, with the same label object as the replay response. Then every `agent_event`. Then `event: end`, `data: {"events", "replay": true, "label"}`.
- **Errors:** 404 when there is no session and no saved run.

### `POST /buildings/{id}/depth`
- **Body:** `{"depth_ft": 4}`, optional `"recipient"`. Starts turn 2: the agent re-plans, re-prices and re-ranks at the new depth, and the trace gets a `replan` event and a "Priority change" decision.
- **Response:** the session status.
- **Errors:** 409 with no session (POST `/run` first) or while a turn runs; 403 if the recipient (given, or the default) is not in `ALLOWED_RECIPIENTS`.

### `POST /buildings/{id}/request_send`
- **Body:** `{}` or `{"recipient": "<in ALLOWED_RECIPIENTS>"}` (default: the first allowed address).
- **What happens:** turn 3. Communications drafts the report and playbook (dossier files), then the agent calls `send_playbook`, which pauses. The stream ends with `waiting_for_approval: true`, after an `awaiting_approval` event.
- **Response:** the session status.
- **Errors:** 409 or 403 as above.

### `POST /buildings/{id}/send?depth_ft=`
- **Body:** `{"approved": true | false, "recipient"?, "note"?}`. With no recipient, the first allowed address is used.
- **While the agent waits for approval:**
  - `true` resumes it (turn 4); its `send_playbook` tool sends. The response is the session status.
  - `false` rejects, with `note` as the reason; the response is the session status.
- **Otherwise:**
  - `true` sends the playbook at `depth_ft` directly. The response is the delivery record `{"building_id", "recipient", "depth_ft", "approved", "at", "status", "detail"}`.
  - `false` returns 400.
- **Delivery `status`:**
  - `sent`: delivered over SMTP.
  - `draft_only`: SMTP is not configured, or `DEMO_MODE=1`. Show `detail`, which reads "draft only, not sent: …".
  - `refused`: not approved, or recipient not allowed.
  - `failed`: SMTP error, given in `detail`.
- **Errors:** 403 when the recipient is not in `ALLOWED_RECIPIENTS`.

### `GET /buildings/{id}/agent`
- **Without a session:** `{"building_id", "session": null, "memory", "last_delivery"}`.
- **With a session:** `{"building_id", "run_id", "running", "turns", "waiting_for_approval", "events", "error", "events_url", "memory", "last_delivery"}`.
  - `turns`: `[{"turn": "assess" | "replan" | "send" | "approval", "seconds", "model_calls", "cost_usd", "interrupted"}]`.
  - `error`: null, or a budget or model error from the last turn.
  - Every POST above that returns "the session status" returns this same object.
- **`memory`** (human corrections the agent remembers):
  - `active_human_corrections`: integer. Corrections a person made through PATCH or DELETE that are still active.
  - `human_corrections`: `[{"id", "asset_id", "action": "patch" | "delete", "changes", "note", "at"}]`.
  - `applied_this_session`: integer. How many assets the agent applied a human correction to during the current session (agent-propagated corrections since the session started). It is 0 without a session.
  - `applied_this_session_asset_ids`: those assets' ids.
  - Inactive corrections (agent copies that no longer match any asset) are never counted.
- **`last_delivery`:** null, or the latest send attempt for this building: `{"status", "recipient", "at", "detail"}`. Status values are as for `/send`.

### `POST /demo/reset` (localhost only) and `GET /demo/state`
- **Reset:** puts the demo in its starting state:
  - every building's full stored survey;
  - exactly one human correction on E and no agent copies;
  - the agent's memory rebuilt;
  - dossiers emptied (the send log is kept);
  - the triage ranking recomputed;
  - no agent sessions, and depth 1 ft.
- **Properties:** no model calls; safe to repeat.
- **Response:** `{"reset_at", "depth_ft": 1.0, "agent_session": null, "baseline_taken_at", "buildings": {"<id>": {"positions_read", "scan_positions", "assets", "human_corrections", "agent_corrections"}}}`.
- **Errors:** 409 while an agent turn runs; 403 from another host.
- **`GET /demo/state`:** returns the object the last reset returned, or `{"depth_ft": 1.0, "reset_at": null}` if there has been none.

### Related
- The fixture building `fixture-1`: `/run` and `/events` replay the fixture trace (`fixtures/agent_events.json`).
- `GET /buildings/{id}/runs/latest` returns the replay object without starting anything.
- `GET /buildings/{id}/dossier` returns every file the agent wrote: `{"building_id", "files": [{"path", "bytes", "modified", "content"}]}`.

## Changes from AGENTS.md section 8

**Building**
- Added `costar_property_id`, `property_subtype` and `size_basis` (always `GBA`).
- Added `improvement_value_usd` and `value_as_of`. Value comes from an assessor value on a CoStar sale comp, not a market value.
- Added `loading_docks_external` and `drive_in_bays` (CoStar). They tell the site scout how many doors to look for.
- Added `matterport_model_ids` (a property can have several scans) and `scan_area_sqft` (a scan can cover only part of the building).
- Added `flood_zone` and `flood_zone_subtype`.
- `in_mapped_flood_zone` now means FEMA `SFHA_TF == "T"`.
- Added `ground_elevation_source`, `aerial_collection` and `aerial_capture_date`.

**EntryPoint**
- Added kind `drive_in` for grade-level doors, distinct from dock-high `dock`.
- Added `image_kind`, `image_xy` and `elevation_source`.
- `lat` and `lng` are now nullable.

**Asset**
- `sweep_id` is renamed `location_id`, the Matterport Model API name.
- Added `matterport_model_id`, `floor_id` and `room_id`.
- `position` is typed `{x, y, z}` or null.
- Added `observations`, so both looks of a re-inspection are kept, and `source` (vision, human or human-propagated) for feedback.

**ScenarioResult**
- Added `depth_reference`, fixed to the slider's meaning.

**Mitigation**
- Added `depth_ft`, `rank` and `kind`.

**AgentEvent**
- Added `id` (sequence number), `building_id` and `data`.

## Changelog

### 1.3.0 (2026-11-14, judge feedback; human lifted the freeze for these changes)

The loss range was a worst-case sum (every item at its low end, or every item at its high end). It is now the median and 80% interval of a simulation (`backend/app/loss/sim.py`, assumptions `C-MC-*`). The old sums are kept only as extreme bounds in the assumptions list (`X-EXTREME-BOUNDS`).

**Meaning changed (same field names, so nothing breaks)**
- `ScenarioResult` / `ScenarioTable.rows[]`: `loss_usd_low/high`, `structure_loss_usd_low/high` and `total_usd_low/high` are the 10th and 90th percentiles. `Triage.loss_by_depth_ft[d].contents/structure/total` `[low, high]` likewise. `Mitigation.avoided_loss_usd_low/high` likewise (the same draws before and after the action).
- Simulated figures are rounded to 3 significant figures.
- Percentiles do not add up: `total_usd_low` is the 10th percentile of contents + structure, not `loss_usd_low + structure_loss_usd_low`.
- `/triage` and `/buildings` rank by the median total (was the high end). `Mitigation.rank` and the payback ratio use the median avoided loss.

**Added (required)**
- `ScenarioResult` and every `ScenarioTable` row: `loss_usd_median`, `structure_loss_usd_median`, `total_usd_low`, `total_usd_median`, `total_usd_high`; `items_in_water` (`of`, `count_low`, `count_high`, `share_low`, `share_high`: contents items the water reaches, from item heights only, no dollar assumption); `top_contributors` (up to 5 `{asset_id, expected_loss_usd, share}`); `standard_contents_usd_median` (Hazus-style contents loss on the same item values, or null).
- `ScenarioTable.assets[].expected_loss_usd`: expected loss per step.
- `ScenarioTable.thresholds`: `first_loss_ft`, `half_items_ft`, `most_items_ft` (80%), `critical_systems[]` (electrical, IT) as `[earliest, latest]` depths, with `heights_from_mesh` / `heights_estimated` counts.
- `ScenarioTable.standard_method`: the Hazus 6.1 default contents and inventory functions used, the citation, the value basis, `compare` at 1, 2, 4 and 6 ft (`ours_median_usd`, `standard_median_usd`, `ratio`, `verdict`: higher, lower or about the same, within 0.8–1.25 times), a plain `statement` and `why_shapes_differ`.
- `Triage.loss_by_depth_ft[d]`: `contents_median`, `structure_median`, `total_median`.
- `Mitigation.avoided_loss_usd_median`.
- Assumption ids: `C-MC-VALUE`, `C-MC-CLASS-CORR` (team-set, `placeholder: true`), `C-MC-HEIGHT`, `C-MC-STRUCT`, `C-MC-DRAWS`, `X-EXTREME-BOUNDS` (per depth in `/scenario`; `X-EXTREME-BOUNDS-1FT`, `-2FT`, `-4FT` and `-6FT` in `/scenario_table`).

**What Codex must change**
1. Show the median as the headline figure, with the 80% interval beside it ("about $92,300, 80% interval $72,300–115,000"), for total, contents and structure, on the building page, the triage map and the mitigation table.
2. Show `items_in_water` beside the dollar figure as the measured fact ("53–64 of 71 items reached").
3. Show `thresholds` (first loss, half, 80%, electrical, IT) as marks on the depth gauge.
4. Show the standard-method `statement` (and `standard_contents_usd_median` at the current step) with its citation.
5. Show `top_contributors` at the current step.
6. List `X-EXTREME-BOUNDS*` with the other assumptions only. Never show them as the range.
7. The fixtures are regenerated. `scenarios.json` now holds simulated percentiles, and the FIXTURE structure curve is in `backend/app/fixtures.py`.

**Part B: the depth tied to real elevations (new endpoint `GET /buildings/{id}/grounding`, schema `grounding.schema.json`)**
- Waterline does not model rainfall, drainage or flow. Each slider step's outside water surface is the estimated floor elevation plus the depth (`steps[]`, ft NAVD 88, with a range).
- `floor`: USGS EPQS ground (3DEP, NAVD 88) in front of the doors that set the floor, plus a slab allowance chosen from the door types: `G-SLAB-GRADE` (drive-in, 0–0.5 ft), `G-SLAB-DOCK` (dock-high, 3.5–4.5 ft) or `G-SLAB-STEP` (0.5–1.5 ft). These are team-set ("assumed range, editable"). The range includes 1 RMSE (0.53 m) of the USGS ground.
- `entry_points[]`: mapped doors ranked by the ground in front of them, lowest first. `first_door.sentence` says which door water reaches first and by how much.
- `fema_1pct`: FEMA's 1% annual-chance water surface from NFHL cross-sections (layer 14 `WSEL_REG`), with the nearest BFE line (layer 16 `ELEV`) as a check. It carries `V_DATUM` and distance, and `relative_to_floor_ft` (> 0 is depth inside, < 0 stays below the floor) with a plain `sentence`.
- `reference_levels[]`: gauge marks with `depth_above_floor_ft` (and low/high), `source` and `sentence`: `fema-1pct`, and `lowest-door-ground` (or `lowest-adjacent-ground` when no door is mapped).
- `datum`: NAVD 88 on both sides. `match: false` drops the FEMA mark.
- `method`: the two-sentence method statement. `assumptions`: the `G-*` ids.
- `Building.ground_elevation_ft` is NAVD 88 (confirmed from USGS documentation). It is still the single EPQS value at the CoStar point.
- Returns 503 until `python -m app.loss.grounding` has run for the building. The result is cached, so `DEMO_MODE` serves it.

**What Codex must change (part B)**
8. Mark `reference_levels` on the depth gauge at `depth_above_floor_ft`. A negative value means "stays N ft below this floor": show it under the zero mark with its `sentence`.
9. Show the outside water surface for the current step (`steps[i].water_surface_ft`, ft NAVD 88) beside the depth, and `method` near the slider.
10. On the aerial panel, order the entry points by `grounding.entry_points[].rank` and show `first_door.sentence`.
11. Badge the `G-SLAB-*` and `G-LEVEL-TOL` assumptions "assumed range, editable".

### 1.2.2 (2026-11-14, requested by Codex; no schema changed)

- New "Agent flow (API)" section above: run, events (with `?after`), depth, request_send, send, agent, and demo reset and state.
- `GET /buildings/{id}/agent` (and every POST that returns the session status) adds `memory` (`active_human_corrections`, `human_corrections`, `applied_this_session`, `applied_this_session_asset_ids`) and `last_delivery` (`status`, `recipient`, `at`, `detail`, or null).

### 1.2.1 (2026-11-14, human decisions on the stored survey; no schema shape changed)

- **The stored survey never shrinks.** An agent run adds to a building's survey or re-checks it, and never replaces it with a smaller one. `/triage`, `/buildings/{id}`, `/scenario_table` and the agent all describe the same stored survey.
- **`Triage.positions_read` / `scan_positions`** is the stored survey, shown as "N of M positions read" for every building. Only the description text changed.
- **`Triage.contents_assets`** now excludes road vehicles (`V-VEHICLE`) as well as building fabric (`A-FIN`). This is the same count the agent reports. Vehicles are named in `note`.
- **Room names are unique within a building** (`Asset.room`): two rooms the scan calls "Office" become "Office" and "Office 2", so each mitigation names one room.
- **Agent replay:** `POST /buildings/{id}/run` with `{"replay": true}`, or any `/run` under `DEMO_MODE=1` without `{"live": true}`, returns the last saved run labelled `REPLAY`. `GET /buildings/{id}/events?replay=1` streams it: a first `replay` SSE event carries the label, run id and recording time, and `end` repeats `replay: true`. `GET /buildings/{id}/runs/latest` returns the same label. Under `DEMO_MODE=1` the replay is the pinned hero run.

**What Codex must change**
1. Show "N of M positions read" from `/triage` (`positions_read`, `scan_positions`) on the map and on the building page.
2. "Replay last run" button: `POST /run {"replay": true}`, then open `events_url`. While it plays, show the `label` from the `replay` event ("REPLAY … not a live run").
3. Remove any quick-scan control and the `quick_scan` field from `POST /run`: it is a development-only flag now and the API ignores it.
4. Assumptions with `placeholder: true` (value classes V-*, mitigation costs M-*): badge them and call them "assumed range, editable" with the id, not PLACEHOLDER. The flag stays `true` in the data.
5. The playbook is the "Pre-storm playbook" (no "72-hour").
6. `GET /events?after=<last event id>` (or the `Last-Event-ID` header) sends only events you have not seen; without it, each connection resends the session from its start.
7. `POST /send` with `{"approved": true}` and no recipient uses the first allowed address.
8. Demo reset: `POST /demo/reset` (localhost) returns the starting state with `depth_ft: 1`; `GET /demo/state` returns it again.
9. Fixture: `fixtures/building.json` `size_sqft` is now 72,000 and `scan_coverage` 0.25 (it matched a real building's size by coincidence).

### 1.2.0 (2026-11-14, approved by the human)

**New endpoints and schemas**
- `GET /buildings/{id}/scenario_table` returns `ScenarioTable`: the loss at every slider step from 0 to 8 ft in 0.25 ft steps, with each asset's damage fraction per step. Each row equals `GET /scenario` at that depth. The fixture building supports it.
- `GET /triage?depth_ft=1|2|4|6` returns `Triage`: every building ranked by total loss, labelled `surveyed` (with positions read and contents count) or `structure only`. `?fixture=1` returns the fixture row.

**Contents loss is now gradual**
- Each asset loses a fraction of its value that rises with the water above its lowest vulnerable point, reaching 1 at a class-specific critical height.
- The low end uses the top of the height range and the class's low value; the high end uses the bottom of the range and the high value.
- `likely` and `possible` keep their meaning. The method is assumption `C-CONTENTS-DEPTH`.
- `ScenarioResult` is unchanged, but its contents numbers changed. `fixtures/scenarios.json`, `scenario_2ft.json` and `mitigations.json` were regenerated from the backend code; structure numbers are unchanged.

**Values come from value classes**
- `Asset.value_basis` is now one of 15 value classes in `backend/app/loss/assumptions.yaml` (for example `V-FORKLIFT`, `V-MACHINE-TOOL`, `V-RACKED-INV`), or `V-VEHICLE`, or `A-FIN`.
- `V-VEHICLE` is a road vehicle: its value is 0 and it is not in contents loss. It is listed as a movable asset at risk (`ScenarioTable.assets[].movable`).
- `A-FIN` is building fabric, already priced by the structure curve.

**What Codex must change**
1. Slider: fetch `/buildings/{id}/scenario_table` once per building. At step `i`, read `rows[i]` (contents, structure, totals, `assets_hit`) and each asset's `fraction_low[i]` and `fraction_high[i]`. Remove client-side loss computation.
2. Asset colours: an asset is red when it is in `rows[i].assets_hit`. Shading by `fraction_high[i]` is optional.
3. Triage map: call `/triage?depth_ft=2`, use `rank`, and show the `status` label. A `structure only` building must not look comparable to a surveyed one.
4. Vehicles: show assets whose table entry has `movable: true` in a "Movable assets at risk" list, not in the contents total. "Drive vehicles to high ground" is a mitigation with `kind: "other"` and `basis: "M-MOVE-VEHICLES"`; its avoided loss is 0 by design, and its `payback_note` says why.
5. Corrections: `PATCH /buildings/{id}/assets/{asset_id}` also accepts `value_basis` (a class id) and `value_usd_low` / `value_usd_high`. After a PATCH or DELETE, refetch `scenario_table`.
6. Update any copies of the fixture numbers (contents values changed).

### 1.1.0 (2026-11-14, approved by the human; both agents told)

- **`Building.id` is a slug**, for example `building-a` or `fixture-1`. It must match `^[a-z0-9]+(-[a-z0-9]+)*$`, and every `building_id` field in the other schemas uses the same pattern.
- **`Building.costar_property_id` is removed.** The CoStar PropertyId stays in the server's git-ignored mapping (`data/cache/shortlist.json`). It never appears in API responses, URLs, the UI or committed files.
- **`Building.value_source`** carries no CoStar ids.
- **`Building.scan_coverage` is added:** `min(scan_area_sqft / size_sqft, 1)`. It is capped at 1 because a scan can measure more floor than CoStar's GBA (covered outdoor areas, mezzanines, or an out-of-date GBA). Interior loss covers the scanned area only, and structure loss is scaled by this share.

### 1.0.0 (2026-11-14)

First frozen version.
