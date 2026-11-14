# Demo facts

These are the real figures for the pitch, checked against the backend on 2026-11-14 after `python -m app.demo reset`. Buildings are named by letter only. Every dollar figure is a low–high range at a water depth the user chooses (a scenario, not a forecast).

## The one-liner numbers

- **E is outside FEMA's 1% annual-chance flood area (zone X) and still loses $24,758–219,063 at 1 ft of water inside.**
- **E's survey:** all 49 of 49 scan positions read. 71 contents items worth $81,260–431,200, plus 14 road vehicles listed separately (movable, not in the loss).
- **Measured heights:** about three-quarters of item heights are measured from the 3D scan's mesh, not guessed (76% of 380 items across all eight buildings).
- **A full agent run on E costs $0.13 and takes 48 seconds:** assess at 1 ft, re-plan at 4 ft, draft, wait for approval.

## Loss ranges (total = contents + structure)

| Building | Depth | Contents | Structure | Total |
|---|---|---|---|---|
| E | 1 ft | $17,783–184,187 | $6,975–34,876 | $24,758–219,063 |
| E | 2 ft | $44,160–300,299 | $24,413–69,753 | $68,573–370,052 |
| E | 4 ft | $74,195–407,562 | $34,876–136,018 | $109,071–543,580 |
| B | 1 ft | $37,211–324,446 | $3,141–15,705 | $40,352–340,151 |
| B | 2 ft | $104,942–628,382 | $10,993–31,410 | $115,935–659,792 |
| B | 4 ft | $180,403–885,700 | $15,705–61,249 | $196,108–946,949 |

**After the hero run, E's figures move slightly,** because the agent applies the person's desk correction to one more desk. These are the figures the replayed trace quotes; in demo mode the UI shows them once the replay starts:

| Building | Depth | Total |
|---|---|---|
| E | 1 ft | $24,582–217,463 |
| E | 2 ft | $68,237–367,652 |
| E | 4 ft | $109,011–543,580 |

## Survey

| | E | B |
|---|---|---|
| FEMA zone | X (outside the 1% area) | AE (inside) |
| Scan positions read | 49 of 49 | 11 of 11 |
| Assets found | 85 | 56 |
| Contents items | 71 | 53 |
| Road vehicles (movable, not in the loss) | 14 | 2 |
| Building fabric (priced by the structure curve) | 0 | 1 |
| Contents value | $81,260–431,200 | $195,000–890,000 |
| Item heights measured from the mesh | 64 of 85 (75%) | 42 of 56 (75%) |

- **All eight buildings:** 288 of 380 item heights (76%) are measured from the mesh. The rest are visual estimates at lower confidence, mostly because the item is not hit by a mesh ray or runs off the bottom of the panorama.
- **Geometry error, measured:**
  - Rays to the floor land within 2 cm of it (median −0.019 m on H, −0.002 m on D; worst 0.11 m).
  - The mesh ceiling matches Matterport's own ceiling height within 0.7 cm (median).
  - Door heads read within about ±5 cm.
  - The survey allows ±0.15 ft (about ±5 cm) when it checks the mesh against the visual estimate.

## The agent run on E (pinned as the demo replay)

- **Run:** `20261114T201733Z-e6e0f5`, driven through the API the way the UI drives it. 82 trace events.
- **Time and cost:** 48.0 s in total, 29 model calls, $0.134.

  | Turn | Time | Cost |
  |---|---|---|
  | Assess at 1 ft | 34.5 s | $0.066 |
  | Re-plan at 4 ft | 6.7 s | $0.034 |
  | Draft and request send | 3.4 s | $0.023 |
  | Approval | 1.3 s | $0.011 |

- **The survey reads cached vision answers,** so the run itself spends nothing on vision. A first survey from scratch costs about $0.006 per scan position (median of 133 survey calls).
- **Survey batches:** the largest room first (27 of 49 positions, 55% of the scan, seen as a warehouse), then the second room (8 positions, an office), then the five small rooms together (14 positions).
- **Discrepancy (exact trace text):** "Layer discrepancy: The aerial images show 3 drive-in doors but CoStar records 4. Neither source is taken as right: a door may be hidden by trucks, trees or the viewing angle, or sit on a wall no view shows. Confidence of every drive-in entry point lowered by 20%."
- **Memory:**
  - **The person's correction:** an office desk's lowest vulnerable part set to 1.5–1.8 ft, with the note "Desks here are steel-frame on legs; the wooden drawers start 1.5 ft up".
  - **The agent's decision (exact trace text):** "Applied human correction corr-bc2ca834 (height_ft_low -> 1.5, height_ft_high -> 1.8) to 1 similar asset (building-e-a82): Applied to building-e-a82 (office desk). Skipped building-e-a1 (conference table and chairs), building-e-a5 (chair), building-e-a74 (chairs), and building-e-a85 (chair) because they are not desks. Skipped building-e-a6 (wooden office desk) because it is a wooden desk rather than steel-frame on legs."
- **Re-plan, 1 ft → 4 ft:**
  - Moving office floor stock onto racking rises from rank 3 to 2. Avoided loss goes from $792–8,778 to $3,544–25,111.
  - Moving the second office's floor stock rises from rank 11 to 3.
  - The 2 ft barriers stop helping at 4 ft.
- **Approval:** the run stops with "Waiting for a person to approve send_playbook … Nothing is sent before Approve." On approval the send is recorded as "draft only, not sent" until SMTP is configured.

## Other pinned replays (demo mode)

Each was recorded live after a demo reset (1 ft, then 4 ft, then draft, then approve) and pinned as that building's replay. The figures in each trace match the data after a reset.

| Building | Run | Time | Model calls | Agent cost | Vision reads during the run |
|---|---|---|---|---|---|
| G | `20261114T212113Z-8cb087` | 80.2 s | 25 | $0.084 | 12 new positions read live ($0.065), so G is now 27 of 27 |
| B | `20261114T212235Z-505bb3` | 38.4 s | 28 | $0.093 | none (all 11 cached). Two re-looks raised confidence on a press and a lathe |
| D | `20261114T212632Z-eb9adf` | 69.7 s | 31 | $0.098 | 3 positions read live, so D is now 33 of 33 (the first D run also read 15 new positions) |

- **The runs are slower than E's because they read positions live;** a replay paces gaps at most 3 s.
- **A, C, F and H have no pinned run.** In demo mode, "Run agent" on them returns 404.

## Buildings outside the mapped flood zone

Five of the eight buildings are outside FEMA's 1% annual-chance flood area (zone X). Ranked by total loss at 2 ft (high end):

| Rank at 2 ft | Building | FEMA zone | Total at 2 ft | Positions read |
|---|---|---|---|---|
| 1 | G | X | $290,757–990,538 | 27 of 27 |
| 2 | B | AE | $115,935–659,792 | 11 of 11 |
| 3 | D | AE | $92,906–545,008 | 33 of 33 |
| **4** | **E** | **X** | **$68,573–370,052** | **49 of 49** |
| 5 | C | AE | $85,857–244,578 | 15 of 49 |
| 6 | F | X | $33,687–229,383 | 15 of 21 |
| 7 | A | X | $58,367–227,292 | 13 of 57 |
| 8 | H | X | $73,480–219,657 | 14 of 96 |

- **G ranks first mostly on structure loss.** Its full survey found only 16 contents items.
- **B, D, E and G are fully surveyed.** For A, C, F and H, contents loss covers only the positions read: a floor, not a whole-building estimate.

## Say carefully

- **The value ranges are team-set assumptions** ("assumed range, editable"), not quotes. A person can correct any of them.
- **Hazus check:** E's contents loss range contains the FEMA Hazus-style figure. B's is higher: the middle of its range is about 3 times Hazus, and the high end about 7.4 times.
- **Depths are scenarios.** Waterline does not forecast floods.
