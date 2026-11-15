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
- Each item's value and lowest vulnerable point are uncertain. `run_scenario` simulates them 4,000 times (C-MC-*): values lognormal between the class's low and high (10th and 90th percentiles), items of one class moving together (correlation 0.5), heights anywhere in their range.
- It reports the **median** and the **80% interval** (10th–90th percentile). The old "every item at its low end" and "every item at its high end" sums are only extreme bounds, listed in the assumptions (X-EXTREME-BOUNDS).
- It also reports what needs no dollar assumption: how many contents items the water reaches (from measured heights), and the Hazus-style contents loss on the same item values for comparison.
- An asset is **likely** hit when the depth reaches its height range's top, and **possible** when it reaches the bottom.
- Values come from 15 value classes (for example V-FORKLIFT, V-MACHINE-TOOL, V-RACKED-INV). They are team-set assumptions, shown as "assumed range, editable" with their id.
- Road vehicles (V-VEHICLE) are movable assets at risk, not contents. Recommend driving them to high ground.
- Building fabric (A-FIN) is priced by the structure curve.

## Structure loss
Structure loss = FEMA Hazus 6.1 depth-damage % for the occupancy (COM1, COM2 or IND2) × the assessor improvement value from CoStar × scan coverage. Only the scanned area is assessed.

## Mitigations
- `rank_mitigations` ranks fixes by avoided loss per dollar at exactly one depth. The order changes with depth.
- A 2 ft barrier helps only up to 2 ft. Raising items helps until the water passes the new height.
- When the depth changes, re-run the scenario and the ranking. Say which fixes moved up or down, and why.

## Writing numbers
- Every dollar figure is a median with its 80% interval ("about $92,300 (80% interval $72,300-115,000)"), copied from a tool result.
- Never quote the extreme bounds as the range.
- Name the assumptions behind it, and mark placeholders.
