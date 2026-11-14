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

**`contracts/` v1.1.0 is the source of truth and is frozen.** See the changelog in `contracts/README.md`.
- v1.1 makes building ids slugs (`building-a`), removes the CoStar property id from every response, and adds `scan_coverage`, capped at 1.
- The CoStar id lives only in the git-ignored `data/cache/shortlist.json`.

1. **"In the mapped flood zone"** means FEMA `SFHA_TF == "T"` (1% annual chance). Shaded X (0.2%) counts as outside.
2. **Ground floor** means CoStar `numStoriesAboveGrade == 1`.
3. **Value basis** is the assessor improvement value, from deed-level assessments matched to the property's parcel numbers (APNs). The fallback is the assessment on a single-property sale comp. Sale prices are not used, and there are no placeholder values.
4. **Interior loss covers the scanned area only.** Structure loss = Hazus damage % × improvement value × `scan_coverage` (human decision).
5. **Scan coverage above 100% is capped at 100%.** Building E's scan measures 102% of CoStar's GBA (covered outdoor areas, mezzanines, or an out-of-date GBA). Counting more than the whole building would overstate loss.

## D4. Building shortlist (revised 2026-11-14)

**Rules (human decisions):**
- single-storey
- no children's spaces
- an assessor value whose value per sq ft lies within 0.4–2.5× the median of the 62 valued candidates ($68/sq ft)
- scan coverage of 40% or more, best first
- no scans shared between properties
- at least 3 buildings outside the FEMA 1% area
- replacements prefer a named current tenant

Retained buildings keep their letter.

**Changes from v1:**
- A and F (day care centres) were removed as children's spaces.
- B was checked as asked: $33/sq ft, which is 0.49× the pool median and 0.58× the shortlist median. That's inside the band, so B stays.
- The same test flagged the old G at $10/sq ft (0.15×), so it was swapped.
- Cached media for the three removed buildings was deleted.

| Building | Type | FEMA | Scan positions | Scan coverage | Named tenants |
|---|---|---|---|---|---|
| A | Industrial warehouse | X, 0.2% shaded | 57 | 86% | 1 |
| B | Industrial warehouse | AE (1%) | 11 | 53% | 1 |
| C | Flex | AE (1%) | 49 | 47% | 2 |
| D | Industrial warehouse | AE (1%) | 33 | 43% | 0 |
| E | Industrial warehouse | X, 0.2% shaded | 49 | 100% (capped from 102%) | 1 |
| F | Flex showroom | X, 0.2% shaded | 21 | 70% | 1 |
| G | Retail storefront | X, 0.2% shaded | 27 | 63% | 15 |
| H | Industrial warehouse | X, minimal | 96 | 49% | 2 |

H is the story building outside the mapped flood zone, and the first building surveyed.

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

## D7. Models

**Vision and the agent orchestrator run on Gemini** (human decision; Anthropic is optional). The model was chosen from the Gemini models list on 2026-11-14, under the rule "newest stable Flash that accepts images: no `-preview`, no `-latest`, no date suffix". That gives `gemini-3.8-flash`.
- Fallbacks: `gemini-3.7-flash` then `gemini-3.6-flash`, used only on 503 or timeout.
- On the day: 3.8 passed the text test but returned 503 and timed out on image calls (Google reported "high demand"). 3.6 passed both tests.
- Every cached vision response records which model answered.
- `AGENT_MODEL=google_genai:gemini-3.8-flash`. That `provider:model` format was confirmed through the docs-langchain MCP server (`docs.langchain.com/mcp`, queried over HTTP).

## D8. Panorama geometry

**The pixel → 3D mapping is calibrated, not assumed** (`backend/app/survey/geometry.py`, `calibrate.py`).
- The face convention comes from multi-view photo-consistency against the mesh: NCC 0.884 against 0.622 for the next-best of 32 candidates on H, with the same winner on D.
- **Checks:**
  - Down-face centre rays hit the floor at a median z of −0.019 m (H) and −0.002 m (D), worst 0.11 m.
  - The mesh ceiling is within 1 cm of Matterport's own room ceiling heights at the median (office 2.755 m against 2.745 m).
  - Door heads read within about ±5 cm: H's office doors are full height to the 2.74 m ceiling and read 2.69–2.78 m, and its one standard steel exit door reads 2.21 m at the wall just above its frame.
- Asset heights are "measured from mesh" when the mesh and the visual estimate agree, with ±0.15 ft plus the measured box-edge spread. Otherwise they're an estimated range at lower confidence.
- **Building fabric is not contents.** The vision model also reports wall outlets, switches and fixed cabinetry.
  - They stay in the inventory, so the water visibly reaches them.
  - They are classed `finishes` (A-FIN, $0) because the Hazus structure curve already prices them (`interior.FABRIC`, tested).
  - Without this, eight outlets on H were priced at A-ELEC $3,000–25,000 each.

## D9. Structure loss curves

**Structure damage uses FEMA Hazus 6.1 flood structure functions** (`backend/app/loss/curves.yaml`, generated by `python -m app.loss.build_curves`, `placeholder: false`).
- Mapping: retail → COM1, warehouse and distribution → COM2, other industrial and flex → IND2.
- The range is the 25th–75th percentile across the USACE Galveston district functions for the occupancy, widened to include the Hazus default.
- Asset replacement values and mitigation costs are team assumptions, marked `placeholder: true` and labelled PLACEHOLDER.
