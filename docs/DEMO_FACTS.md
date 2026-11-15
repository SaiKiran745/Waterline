# Demo facts

These are the real figures for the pitch. They were checked against the backend on 2026-11-14 after `python -m app.demo reset` (contracts v1.3).
- Buildings are named by letter only.
- **Every dollar figure is a median with its 80% interval** (10th–90th percentile of 4,000 simulated draws). The old worst-case sums are only "extreme bounds".
- Every depth is a scenario the user chooses, tied to elevation. It is not a forecast: Waterline does not simulate rainfall, drainage or how water arrives.

## The one-liner numbers

- **E is outside FEMA's 1% annual-chance flood area (zone X), and at 1 ft of water inside it still loses about $93,600 (80% interval $73,500–117,000).** The old worst-case range was $24,758–219,063.
- **FEMA's 1% flood level on the creek 62 m from E stays only about 1.3 ft below E's floor** (range −3.6 to +1.0 ft, within the uncertainty). FEMA maps E outside the zone, so this level is a reference, not a claim that it applies at E.
- **Measured, with no dollar assumption:** at 1 ft the water reaches 55–66 of E's 71 contents items.
- **E's survey:** all 49 of 49 scan positions read. It found 71 contents items worth about $225,000 (80% interval $176,000–292,000), plus 14 road vehicles listed separately (movable, not in the loss).
- **A full agent run on E costs $0.12 and takes 55 seconds:** assess at 1 ft, re-plan at 4 ft, draft, then wait for approval.

## Loss: median and 80% interval, with the old bounds for comparison

| Building | Depth | Total (median, 80% interval) | Contents | Structure | Old total (extreme bounds) |
|---|---|---|---|---|---|
| E | 1 ft | $93,600 ($73,500–117,000) | $72,200 ($55,600–94,400) | $20,700 ($9,590–31,900) | $24,758–219,063 |
| E | 2 ft | $189,000 ($153,000–232,000) | $141,000 ($110,000–182,000) | $46,700 ($28,700–65,000) | $68,573–370,052 |
| E | 4 ft | $297,000 ($235,000–367,000) | $210,000 ($164,000–272,000) | $84,600 ($44,400–125,000) | $109,071–543,580 |
| B | 1 ft | $136,000 ($101,000–193,000) | $126,000 ($91,100–183,000) | $9,460 ($4,540–14,500) | $40,352–340,151 |
| B | 2 ft | $306,000 ($224,000–439,000) | $284,000 ($202,000–419,000) | $21,300 ($13,300–29,500) | $115,935–659,791 |
| B | 4 ft | $480,000 ($339,000–716,000) | $441,000 ($300,000–677,000) | $38,600 ($20,800–57,000) | $196,108–946,949 |

- **How wide the ranges are** (high end ÷ low end at 1 ft): E's old range spanned 8.8 times; the 80% interval spans 1.6 times. For B, 8.4 times against 1.9 times.
- **Percentiles do not add up.** The total's interval is that of the summed draws, not the sum of the parts' intervals.
- **After the hero run, E's figures move slightly,** because the agent applies the person's desk correction to two more desks. These are the figures the replayed trace quotes, and in demo mode the UI shows them once the replay starts:
  - 1 ft: about $92,300 ($72,300–115,000)
  - 2 ft: about $187,000 ($151,000–230,000)
  - 4 ft: about $297,000 ($235,000–367,000)

## What the scan measures (no dollar assumption)

| | E | B |
|---|---|---|
| Contents items | 71 | 53 |
| Heights measured from the mesh | 52 of 71 | 39 of 53 |
| Items reached at 1 ft | 55–66 (77–93%) | 43–50 (81–94%) |
| Items reached at 2 ft | 63–67 | 48–50 |
| Items reached at 4 ft | 70 | 52–53 |
| First item reached | 0–0.1 ft | 0–0.1 ft |
| Half the items reached | 0–0.5 ft | 0–0.47 ft |
| 80% of items reached | 0.26–1.33 ft | 0.07–0.78 ft |
| First electrical item | 2.21–3.26 ft (1 item) | 0–0.23 ft (2 items) |
| First IT item | 0–0.29 ft (2 items) | none surveyed |

- **How to read the ranges:** "55–66" counts items whose whole height range is under water, then those whose range has merely been reached. Depths read the same way: the earliest from the bottom of each item's height range, the latest from the top.
- **All eight buildings:** 288 of 380 item heights (76%) are measured from the mesh.

## Standard-method comparison (FEMA Hazus 6.1 on the same item values)

The Hazus 6.1 default COM2 functions are used: contents 195 (16, 27, 49 and 63% at 1, 2, 4 and 6 ft) and inventory 46 (19, 33, 54 and 69%), both USACE Galveston. They are applied to the same simulated item values as ours.

| Depth | E: ours | E: Hazus-style | E: ratio | B: ours | B: Hazus-style | B: ratio |
|---|---|---|---|---|---|---|
| 1 ft | $72,200 | $37,900 | 1.9, higher | $126,000 | $73,500 | 1.7, higher |
| 2 ft | $141,000 | $64,600 | 2.2, higher | $284,000 | $124,000 | 2.3, higher |
| 4 ft | $210,000 | $113,000 | 1.9, higher | $441,000 | $225,000 | 2.0, higher |
| 6 ft | $224,000 | $146,000 | 1.5, higher | $456,000 | $289,000 | 1.6, higher |

**Why ours is higher:**
- Hazus applies a building-average percentage from the first inch of water, and never reaches 100% (72% of contents at 8 ft), because a building's contents include things stored above the water.
- Waterline prices only the items the survey saw, from each one's own lowest vulnerable point.
- On E, 89% of the surveyed value sits in items whose lowest vulnerable part may be below 1 ft; on B, 97%.

## Largest contributors (expected loss)

- **E at 1 ft:**
  - two boom lifts, about $8,570 and $8,540 (12% each)
  - lifts and machinery, about $5,340 (7%)
  - a conference table with a monitor, about $2,750
  - a space heater, about $2,220
- **B at 1 ft:**
  - a burn table, about $8,090 (6%)
  - two forklifts, about $7,610 and $7,290
  - a lathe, about $6,700
  - a vertical machine, about $6,510
  - Machine-shop loss is spread over many items.

## Elevation (ft NAVD 88)

| | E | B |
|---|---|---|
| FEMA zone | X (outside the 1% area) | AE (inside) |
| Ground next to the walls | 33.0–33.8 (low east, high north) | 59.8–60.3 (low north, high south) |
| Ground within 40 m | 25.6–34.2 (the creek side drops) | 59.4–60.4 |
| Lowest door | drive-in, east side, 33.2: 0.1 ft below the next door (about level) | drive-in, east side, 60.0: 0.2 ft below the next (about level) |
| Floor estimate | 33.7 (range 31.5–36.0) | 60.3 (range 58.2–62.4) |
| Slab allowance | G-SLAB-GRADE, 0–0.5 ft (drive-in doors; CoStar records 4) | G-SLAB-GRADE (drive-in doors; CoStar records 4) |
| FEMA 1% flood level | 32.4, from 2 cross-sections 62 m away on an unnamed tributary (BFE line 75 m away: 32) | 60.5, from cross-sections 20 m and 83 m away on a bayou (BFE line 147 m away: 61) |
| FEMA 1% level vs floor | stays about 1.3 ft below (−3.6 to +1.0) | about 0.2 ft above (−2.1 to +2.3) |
| Outside water surface at 1 ft inside | 34.7 | 61.3 |

- **Datum:**
  - **USGS:** EPQS interpolates 3DEP (USGS FAQ, updated 2025-07-18), and 3DEP is NAVD 88 over the contiguous US (USGS DEM metadata).
  - **FEMA:** the NFHL lines record `V_DATUM` NAVD88, in feet.
  - Same datum, so there is no conversion.
- **Accuracy:** USGS states an RMSE of 0.53 m (1.74 ft). That is carried into the floor range, and is why FEMA's level can fall either side of the floor on both E and B.
- **Every building** (FEMA 1% level against the estimated floor, central figure):

  | Building | Zone | Position | Range |
  |---|---|---|---|
  | A | X | 1.3 ft below | −4.2 to +1.4 |
  | B | AE | 0.2 ft above | −2.1 to +2.3 |
  | C | AE | 1.8 ft above | −1.3 to +5.2 |
  | D | AE | 2.7 ft above | −0.7 to +6.1 |
  | E | X | 1.3 ft below | −3.6 to +1.0 |
  | F | X | 0.4 ft below | −3.6 to +2.4 |
  | G | X | 3.9 ft below | −6.8 to −1.5 |
  | H | X | 1.5 ft below | −4.3 to +1.4 |

  - **G is the only building whose whole range stays below the floor.** It is dock-high (G-SLAB-DOCK), and its dock apron is the lowest ground: about 4 ft below the floor.
  - **H's nearest FEMA level is 1.4 km away,** a weak reference.
- **No Harvey high-water marks:** FEMA's layer has none within 8 km of any building, and the USGS STN service could not be verified in time.

## The agent run on E (pinned as the demo replay)

- **Run:** `20261115T004152Z-5e946f`, 85 trace events.
- **Time and cost:** 54.6 s in total, 28 model calls, $0.117.

  | Turn | Time | Cost |
  |---|---|---|
  | Assess at 1 ft | 37.5 s | $0.056 |
  | Re-plan at 4 ft | 11.0 s | $0.031 |
  | Draft and request send | 4.5 s | $0.020 |
  | Approval | 1.5 s | $0.010 |

- **The survey reads cached vision answers,** so the run spends nothing on vision. A first survey from scratch costs about $0.006 per scan position (median of 133 survey calls).
- **Doors (exact trace text):** "Doors ranked by the ground in front of them (USGS 3DEP, NAVD 88): The ground is lowest in front of the drive-in door on the east side, 0.1 ft lower than at the next door (door, west), so water collects there first (within 0.5 ft: about level)."
- **Discrepancy (exact trace text):** "Layer discrepancy: The aerial images show 3 drive-in doors but CoStar records 4. Neither source is taken as right: a door may be hidden by trucks, trees or the viewing angle, or sit on a wall no view shows. Confidence of every drive-in entry point lowered by 20%."
- **Memory:**
  - **The person's correction:** an office desk's lowest vulnerable part set to 1.5–1.8 ft, with the note "Desks here are steel-frame on legs; the wooden drawers start 1.5 ft up".
  - **The agent's decision (exact trace text):** "Applied human correction corr-bc2ca834 (height_ft_low -> 1.5, height_ft_high -> 1.8) to 2 similar assets (building-e-a6, building-e-a82): Applied to office desks building-e-a6 and building-e-a82 as the note applies to office desks with elevated drawers. Skipped chairs and conference table (building-e-a1, building-e-a5, building-e-a74, building-e-a85) because the correction note specifically describes desks with legs and elevated wooden drawers."
  - The earlier hero run skipped the wooden desk (a6). This run applied the note's "desks here" to it as well.
- **Re-plan, 1 ft → 4 ft:**
  - Moving office floor stock onto racking rises from rank 3 to 2. Its avoided loss goes from about $3,140 to about $10,800.
  - Raising 17 warehouse equipment items rises from rank 4 to 3.
  - The 2 ft barriers drop out of the top 3.
- **Approval:** the run stops with "Waiting for a person to approve send_playbook … Nothing is sent before Approve." On approval the send is recorded as "draft only, not sent" until SMTP is configured.

## Other pinned replays (demo mode)

Each run was recorded live after a demo reset (1 ft, then 4 ft, then draft, then approve), from cached vision only, and pinned as that building's replay.

| Building | Run | Time | Model calls | Agent cost |
|---|---|---|---|---|
| B | `20261115T004248Z-76d6d3` | 48.2 s | 25 | $0.106 |
| D | `20261115T004505Z-dffbc4` | 51.9 s | 28 | $0.093 |
| G | `20261115T004959Z-c36ae7` | 49.7 s | 25 | $0.093 |

- **D's run re-looked a wire shelving rack** from a neighbouring position, live. The new view raised its height range from 0–2.2 ft to 0–6.5 ft. The demo baseline was retaken with that update: the stored survey never shrinks.
- **The figures match.** After a reset (and, for E, the run's correction), each replay's totals at 1 and 4 ft equal the API's exactly.
- **A, C, F and H have no pinned run.** In demo mode, "Run agent" on them returns 404.

## Ranking at 2 ft (by median total)

| Rank | Building | FEMA zone | Total at 2 ft (median, 80% interval) | Positions read |
|---|---|---|---|---|
| 1 | G | X | $638,000 ($365,000–906,000) | 27 of 27 |
| 2 | B | AE | $306,000 ($224,000–439,000) | 11 of 11 |
| 3 | D | AE | $266,000 ($202,000–359,000) | 33 of 33 |
| **4** | **E** | **X** | **$189,000 ($153,000–232,000)** | **49 of 49** |
| 5 | C | AE | $160,000 ($120,000–199,000) | 15 of 49 |
| 6 | H | X | $145,000 ($93,500–196,000) | 14 of 96 |
| 7 | A | X | $130,000 ($89,400–170,000) | 13 of 57 |
| 8 | F | X | $105,000 ($81,100–141,000) | 15 of 21 |

- **Five of the eight buildings are outside FEMA's 1% area** (zone X).
- **G ranks first mostly on structure loss.** Its full survey found only 16 contents items.
- **B, D, E and G are fully surveyed.** For A, C, F and H, contents loss covers only the positions read: a floor, not a whole-building estimate.
- **The bottom four now rank** C, H, A, F, ordered by the median. Before v1.3 they were ranked by the high end.

## Say carefully

- **The value ranges are team-set assumptions** ("assumed range, editable"), and so is the 0.5 correlation within a class. A person can correct any of them.
- **The 80% interval covers the stated uncertainty only:** value ranges, height ranges and the Hazus structure range. It does not cover items the survey missed.
- **Against Hazus, ours is higher:** 1.5–2.3 times on the same item values. That is because of how the survey prices low items, not because Hazus is wrong.
- **Depths are scenarios tied to elevation.** Waterline does not forecast floods or simulate how water arrives.
- **The FEMA level for E is the nearest mapped one,** 62 m away on a tributary. Treat it as a reference.
- **The floor elevation is an estimate:** ground plus an assumed slab allowance, ±1.74 ft from the USGS accuracy alone.
