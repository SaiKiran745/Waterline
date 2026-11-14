---
name: survey-method
description: How Waterline surveys a building's interior from its Matterport scan and its exterior from aerial images. Use before choosing scan positions, judging asset heights, re-looking at an asset, or ranking entry points.
---

# Survey method

## Reading the scan
- Call `list_scan_positions` first. It lists the areas (rooms of the scan) largest first, with how many positions to read in each.
- By default every scan position is read. Read in batches, largest areas first: the largest room, the next largest, then all the small rooms together.
- Give each batch one short, specific reason in plain words. For example: "the largest room first: 27 of 49 positions, most of the floor and most of what water can reach".
- The stored survey never shrinks: every batch adds to it. Report the stored survey ("N of M positions read"), not just this run.
- In demo mode only cached vision answers are used. Say so.

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
