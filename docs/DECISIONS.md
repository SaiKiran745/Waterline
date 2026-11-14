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

## D10. Demo buildings (2026-11-14)

**Decided (human): H is too empty to be the hero.**
- A contents scout read 3 well-spread scan positions per building, one call each (`python -m app.survey.scout`). Contents assets (fabric excluded) were: A 5, B 14, C 3, D 12, E 17, F 17, G 1. No children's spaces were flagged.
- **Hero, outside the 1% area: E** (industrial warehouse, X shaded).
  - E and F tied at 17.
  - E has 49 scan positions to F's 21, so a 20-position survey of E still means choosing positions, while for F it means reading nearly all of them.
  - E's scan covers the whole building (100% against 70%).
  - E is an active warehouse; F's contents look like private storage (vintage cars, a recliner, a washing machine).
- **Inside the 1% area: B** (machine shop, AE), the richest of B, C and D.
- **Full surveys:** up to 20 positions each, starting from the scout positions. Positions are spread by room, then filled by farthest-point sampling across the building.
- **H stays as it is:** 14 of 96 positions read, with 6 positions still unread after the billing stop.

## D11. Survey rules added 2026-11-14

- **Merge (human):** two sightings are one asset only if their mesh positions are within 0.5 m and the category matches.
  - The same rule is applied again after re-looks.
  - The earlier 1.5 m rule merged H's floor pump with its wall breaker panels.
- **Truncated boxes:** a box that reaches the bottom of the image (row ≥ 985 of 1000) hides the item's lowest part.
  - The height range then starts at the floor (0 ft) and confidence is capped at 0.55, which makes the item eligible for a re-look.
  - Found on E, where a cabinet standing on the floor read 1.4 ft.
- **Re-look answers must be complete:** with optional fields the model answered "found" without heights, so every field is now required.
- **Gemini budget:** see `data/cache/spend.json` and DATA_NOTES section 14. Calls are refused before the total would pass `GEMINI_BUDGET_USD` (3), and HTTP 402 stops a run.

## D12. Contents values and depth damage (2026-11-14)

- **Value classes (human).** The 7 broad categories became 15 value classes in `backend/app/loss/assumptions.yaml`, each with an id, a range, a critical height and a one-line basis.
  - Examples: forklift $12,000–30,000, machine tool $8,000–40,000, racked inventory $2,000–12,000 per rack run.
  - Classes are assigned from the cached vision labels by ordered keyword rules (`app/loss/classes.py`), with no new calls.
  - They remain team assumptions (PLACEHOLDER) and are editable per asset through PATCH.
- **Vehicles (human).** Road vehicles (`V-VEHICLE`) are not in contents loss. They are listed as movable assets at risk, with a "drive vehicles to high ground" mitigation (`M-MOVE-VEHICLES`) and playbook section. Forklifts and lifts stay equipment.
- **Gradual damage (human; `C-CONTENTS-DEPTH`).**
  - Damage fraction = (depth − lowest vulnerable point) ÷ critical height, capped at 1.
  - The critical height is the class value, capped by the item's own height measured from the mesh (top of its box).
  - Low end: lowest point at `height_ft_high`, low value. High end: lowest point at `height_ft_low`, high value.
  - Tested: zero at zero depth, never decreasing, low ≤ high, including 200 random assets.
- **Duplicates (human).** Sightings merge when they are the same value class and within 0.5 m, or within 1.5 m when the labels share a specific noun (generic words such as "electrical" don't count).
  - Assets: E 60 → 48, B 63 → 54, H 11 → 11.
- **Confidence.** Small boxes (under about 50 × 50 of 1000), items more than 10 m away, and boxes cut by the left, right or top image edge each multiply confidence by 0.85.

## D13. The agent (deepagents 0.7.38, 2026-11-14)

- **Structure.** One orchestrator and six sub-agents (site-scout, interior-surveyor, market-analyst, scenario-builder, mitigation-planner, communications), each with only its own tools. The patterns follow `../hack-princeton-intro-to-deep-agents`.
- **Harness features:**
  - planning (`write_todos`);
  - a dossier at `/dossier/<id>/` in `StateBackend`, copied to `data/cache/agent/dossier/` after each turn;
  - memory at `/memories/` in a SQLite `StoreBackend`, holding human corrections written by PATCH and DELETE;
  - skills `survey-method` and `loss-method`;
  - a human-in-the-loop interrupt on `send_playbook`, with a SQLite checkpointer.
- **Tools are the real survey, site, loss and report code.** They emit their own AgentEvents. Stream translation adds plan, re-plan, delegation, file and approval events. Every event is validated against the contract and saved for replay.
- **Demo mode** offers only scan positions with cached vision answers, and the trace says so. Every model call is priced into `spend.json` and stopped before the budget.
- **First complete live run on E:**
  - 66 model calls; 393,758 input and 26,058 output tokens; $0.39; 127 s.
  - An earlier run never called `send_playbook`, so the instruction now says to call the tool.
- **Not built yet:** email delivery (Phase 5B). An approved send is recorded and nothing leaves the machine.

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

**Vision and the agent orchestrator run on Gemini** (human decision; Anthropic is optional). The model was first chosen from the Gemini models list on 2026-11-14, under the rule "newest stable Flash that accepts images: no `-preview`, no `-latest`, no date suffix". That gave `gemini-3.8-flash`.
- **Changed the same day (human): `GEMINI_MODEL=gemini-3.6-flash` and `AGENT_MODEL=google_genai:gemini-3.6-flash`, with no fallbacks.** 3.8 never answered an image call. 3.6 is priced at $0.75 / $3.75 per 1M input / output tokens (Standard tier, to 2026-12-31).
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
