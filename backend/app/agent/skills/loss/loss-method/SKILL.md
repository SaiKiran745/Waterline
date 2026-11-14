---
name: loss-method
description: How Waterline prices flood loss and ranks fixes. Use before running a scenario, comparing depths, ranking mitigations or writing numbers into a report.
---

# Loss method

## The depth
The depth is interior water above the ground-floor slab, 0 to 8 ft. It is a scenario the user chose, never a forecast. Always say "at N ft".

## Contents loss
- Assumption `C-CONTENTS-DEPTH`: each asset loses a fraction of its value.
  - The fraction is (depth − its lowest vulnerable point) ÷ the critical height of its value class, capped at 1.
  - The critical height never exceeds the item's own height measured from the 3D scan.
- The low end uses the top of the height range and the class's low value. The high end uses the bottom of the range and the high value.
- An asset is **likely** hit when the depth reaches its height range's top, and **possible** when it reaches the bottom.
- Values come from 15 value classes (for example V-FORKLIFT, V-MACHINE-TOOL, V-RACKED-INV). They are team assumptions, labelled PLACEHOLDER.
- Road vehicles (V-VEHICLE) are movable assets at risk, not contents. Recommend driving them to high ground.
- Building fabric (A-FIN) is priced by the structure curve.

## Structure loss
Structure loss = FEMA Hazus 6.1 depth-damage % for the occupancy (COM1, COM2 or IND2) × the assessor improvement value from CoStar × scan coverage. Only the scanned area is assessed.

## Mitigations
- `rank_mitigations` ranks fixes by avoided loss per dollar at exactly one depth. The order changes with depth.
- A 2 ft barrier helps only up to 2 ft. Raising items helps until the water passes the new height.
- When the depth changes, re-run the scenario and the ranking. Say which fixes moved up or down, and why.

## Writing numbers
- Every dollar figure is a low–high range.
- Name the assumptions behind it, and mark placeholders.
- Never round a range into a single number.
