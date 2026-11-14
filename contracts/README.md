# Contracts

**FROZEN: version 1.1.0, 2026-11-14.** Change these files only when a human says both agents (Claude Code on `backend/`, Codex on `frontend/`) have been told.

This folder is the source of truth for data shapes. Where it differs from the sketch in AGENTS.md section 8, this folder wins.

| Schema | Fixture | One record is |
|---|---|---|
| `building.schema.json` | `fixtures/building.json` | One building, from CoStar, Matterport, FEMA, USGS and Vexcel |
| `entry_point.schema.json` | `fixtures/entry_points.json` | A place water gets in, marked on a Vexcel image |
| `asset.schema.json` | `fixtures/assets.json` | A flood-vulnerable item seen in a Matterport panorama |
| `scenario_result.schema.json` | `fixtures/scenario_2ft.json`, `fixtures/scenarios.json` (0, 1, 2, 4, 8 ft) | The loss at one user-chosen depth |
| `mitigation.schema.json` | `fixtures/mitigations.json` (5 fixes, each at 1, 2 and 4 ft) | One ranked fix |
| `agent_event.schema.json` | `fixtures/agent_events.json` | One agent step on the SSE stream |

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

### 1.1.0 (2026-11-14, approved by the human; both agents told)

- **`Building.id` is a slug**, for example `building-a` or `fixture-1`. It must match `^[a-z0-9]+(-[a-z0-9]+)*$`, and every `building_id` field in the other schemas uses the same pattern.
- **`Building.costar_property_id` is removed.** The CoStar PropertyId stays in the server's git-ignored mapping (`data/cache/shortlist.json`). It never appears in API responses, URLs, the UI or committed files.
- **`Building.value_source`** carries no CoStar ids.
- **`Building.scan_coverage` is added:** `min(scan_area_sqft / size_sqft, 1)`. It is capped at 1 because a scan can measure more floor than CoStar's GBA (covered outdoor areas, mezzanines, or an out-of-date GBA). Interior loss covers the scanned area only, and structure loss is scaled by this share.

### 1.0.0 (2026-11-14)

First frozen version.
