---
name: survey-method
description: How Waterline surveys a building's interior from its Matterport scan and its exterior from aerial images. Use before choosing scan positions, judging asset heights, re-looking at an asset, or ranking entry points.
---

# Survey method

## Choosing scan positions
- Call `list_scan_positions` first. Read the rooms and the floor-plan coordinates (metres).
- Choose up to 20 positions. Cover every room at least once.
- In large rooms, also pick positions far apart, so one view does not hide what another sees.
- Prefer rooms where contents gather: warehouses, shops, server and electrical rooms, offices with equipment.
- Give a short, specific reason for every position. For example: "farthest from the other picks in the Warehouse, near the east roll-up doors".
- In demo mode only positions with cached vision answers are offered. Say so; do not pretend they were chosen from all positions.

## Reading heights
- Heights come from the 3D mesh where the mesh and the vision estimate agree ("measured from mesh").
- Otherwise the height is an estimated range at lower confidence.
- Confidence is also lowered for small, distant or edge-cut boxes, and for boxes cut by the bottom of the image (the lowest part is hidden, so the floor is assumed).

## Looking again
- For every contents asset below confidence 0.6, call `relook_asset`. Start with the most valuable classes: machine tools, forklifts and lifts, electrical gear, racked inventory.
- A re-look uses the nearest neighbouring scan position. Report the before and after height and confidence, and whether the answer came from the cache.
- Never re-look building fabric (`A-FIN`) or vehicles (`V-VEHICLE`).

## Entry points
- `find_entry_points` reads every aerial view at once and ranks openings: grade-level drive-in and personnel doors first, then ramps, then dock-high doors.
- Compare the counts with CoStar's drive-in and dock counts and say whether they agree.
- Ground elevation is context only. A threshold height is never invented.

## Privacy
Panorama faces showing identifiable people, children's spaces or personal documents are screened out and never shown.
