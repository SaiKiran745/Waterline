# Contracts

**FROZEN: version 1.2.0, 2026-11-14.** Change these files only when a human says both agents (Claude Code on `backend/`, Codex on `frontend/`) have been told.

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

All schemas are JSON Schema draft 2020-12 with `additionalProperties: false`. Every field is required; unknown values are `null`, never omitted. Each schema property's `description` names the source field it comes from.

Fixtures are fake ("FIXTURE, not real data") and contain no sponsor data. Phase 1 expanded them without changing any schema:
- 25 assets in 5 rooms
- 3 entry points
- scenarios at 0, 1, 2, 4 and 8 ft, computed with the AGENTS.md section 9 rule (depth 0 hits nothing)
- 5 mitigations, each evaluated at 1, 2 and 4 ft, so the ranking changes between 1 ft and 4 ft
- a 40-event agent trace with a plan, a scan-position choice, a low-confidence re-look, a re-plan and an approval wait

`backend/tests/test_contracts.py` validates every fixture.

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

### 1.2.1 (2026-11-14, human decisions on the stored survey; no schema shape changed)

- **The stored survey never shrinks.** An agent run adds to a building's survey or re-checks it, and never replaces it with a smaller one. `/triage`, `/buildings/{id}`, `/scenario_table` and the agent all describe the same stored survey.
- **`Triage.positions_read` / `scan_positions`** is the stored survey, shown as "N of M positions read" for every building. Only the description text changed.
- **`Triage.contents_assets`** now excludes road vehicles (`V-VEHICLE`) as well as building fabric (`A-FIN`). This is the same count the agent reports. Vehicles are named in `note`.
- **Room names are unique within a building** (`Asset.room`): two rooms the scan calls "Office" become "Office" and "Office 2", so each mitigation names one room.
- **Agent replay:** `POST /buildings/{id}/run` with `{"replay": true}`, or any `/run` under `DEMO_MODE=1` without `{"live": true}`, returns the last saved run labelled `REPLAY`. `GET /buildings/{id}/events?replay=1` streams it: a first `replay` SSE event carries the label, run id and recording time, and `end` repeats `replay: true`. `GET /buildings/{id}/runs/latest` returns the same label. `{"quick_scan": N}` on `/run` is an optional partial survey, off by default.

**What Codex must change**
1. Show "N of M positions read" from `/triage` (`positions_read`, `scan_positions`) on the map and on the building page.
2. "Replay last run" button: `POST /run {"replay": true}`, then open `events_url`. While it plays, show the `label` from the `replay` event ("REPLAY … not a live run").
3. Any quick-scan control must be labelled "Quick scan (partial survey)" and off by default.

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
