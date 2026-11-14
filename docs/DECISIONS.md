# Decisions

The evidence for each decision is in `docs/DATA_NOTES.md`. Phase 0 ran on 2026-11-14 and the human decisions were made the same day.

Buildings are named "Building A" to "Building H" in committed files. The mapping to CoStar ids, names, addresses and Matterport models is only in `data/cache/shortlist.json`, which is git-ignored.

## D1. Flood from below, or the roof-ponding fallback?

**Decided: flood from below.** 141 Houston retail, industrial and flex properties are single-storey with scans, so every one of their scans is on the ground floor. The roof-ponding fallback is not needed.

## D2. 3D water view

**Decided (human):**
- **Main view: option B,** our own three.js scene on the downloaded Matterport mesh, with a water plane at `depth_ft × 0.3048` m.
- **Safety net: option C.**
- **Optional extra: option A** (Bundle SDK).

The backend serves the mesh from `/media/<id>/mesh/mesh_50k.obj`. The mesh is untextured: the 50k OBJ has no texture coordinates, and the textures for the 500k OBJ are not downloadable through the API.

## D3. Contracts

**`contracts/` v1.0.0 is the source of truth and is frozen.** No schema changed in Phase 1. The fixtures were expanded: see `contracts/README.md`.

1. **"In the mapped flood zone"** means FEMA `SFHA_TF == "T"` (1% annual chance). Shaded X (0.2%) counts as outside.
2. **Ground floor** means CoStar `numStoriesAboveGrade == 1`.
3. **Value basis** is the assessor improvement value, from deed-level assessments matched to the property's parcel numbers (APNs). The fallback is the assessment on a single-property sale comp. Sale prices are not used, and there are no placeholder values.
4. **Interior loss covers the scanned area only** (human decision). The API exposes `scan_area_sqft` and `size_sqft` on every Building, so the UI can show "scan covers X of Y sq ft". Structure loss uses the improvement value of the whole building.

## D4. Building shortlist

**Rules (human decision):**
- single-storey
- an assessor value is present
- the best scan coverage, aiming for 40% or more
- at least 2 outside the FEMA 1% area, including the 96-position industrial building if it has a value (it does)

**Selection** (`python -m app.sources.shortlist`):
1. Use every qualifying building inside the 1% area.
2. Fill the remaining places with the best-covered buildings outside it.
3. Skip scans that are attached to more than one CoStar property.

| Building | Type | FEMA | Scan positions | Scan covers | Assessor value |
|---|---|---|---|---|---|
| A | Retail (day care) | AE (1%) | 15 | 62% | yes |
| B | Industrial warehouse | AE (1%) | 11 | 53% | yes (7 parcels) |
| C | Flex | AE (1%) | 49 | 47% | yes |
| D | Industrial warehouse | AE (1%) | 33 | 43% | yes |
| E | Industrial warehouse | X, 0.2% shaded | 49 | 102% | yes |
| F | Retail (day care) | X, minimal | 59 | 96% | yes |
| G | Industrial warehouse | X, 0.2% shaded | 28 | 89% | yes |
| H | Industrial warehouse | X, minimal | 96 | 49% | yes |

- **Story building:** H is the 96-position building outside the mapped flood zone.
- **Strongest in-zone candidates:** C and D, which have the most scan positions inside the 1% area.

## D5. Matterport tokens

**Decided (human):** read-only and server-side only.
- `backend/app/sources/matterport.py` refuses any GraphQL mutation or subscription before a request is built (tested in `backend/tests/test_sources.py`).
- Only `NEXT_PUBLIC_MATTERPORT_SDK_KEY` may reach the front end.

## D6. Elevation and entry points

**Decided (human):**
- Stop work on Vexcel elevation models and roof heights.
- Ground elevation (USGS EPQS) is shown as context only.
- Entry points are ranked by type and image evidence, then cross-checked against CoStar's dock count (`loading_docks_external`) and drive-in door count (`drive_in_bays`).
- `threshold_elevation_ft` stays null.
