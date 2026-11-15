# Waterline Design System

Read this before building or changing any UI. The working reference is `docs/ui-reference.html`; where this file and the reference disagree, this file wins.

## Idea

**Storm night at the gauge.** The building is lit on a dark stage. Water rises inside it. A yellow staff gauge, like the ones bolted to bridge piers, stands at the left edge and is the control. One huge figure says what the water costs.

Everything else stays quiet so those three things are what a judge remembers: the water, the gauge, the number.

Audience: lenders, insurers and property managers, seen on a projector from across a room.

## Colors

Only three colours carry meaning. Do not add a fourth.

| Token | Hex | Use |
|---|---|---|
| `--night` | `#061217` | Page background, outer edge of the stage |
| `--night-2` | `#0B1E26` | Mid stage |
| stage glow | `#12313D` | Centre of the radial stage light behind the building |
| `--glass` | `rgba(8,24,31,.74)` | Rail and floating controls, with 14px backdrop blur |
| `--line` | `rgba(255,255,255,.10)` | Hairlines and panel borders |
| `--text` | `#EDF4F4` | Primary text and the loss figure |
| `--muted` | `#93A9B0` | Secondary text |
| `--water` | `#3CC6EA` | Water surface, the gauge level tag, the selected tab |
| `--water-deep` | `#0D6C92` | Water body, submerged part of the gauge |
| `--gauge` | `#F6C61A` | The staff gauge, the primary button, and anything that needs a person |
| `--on-gauge` | `#11161A` | Text and ticks on yellow |
| `--dry` | `#74D6BC` | Asset marker: not reached |
| `--part` | `#FFB238` | Asset marker: partly damaged |
| `--lost` | `#FF5B3D` | Asset marker: lost |

Meaning:
- **Cyan is water.** Never use it for buttons or links.
- **Yellow is the gauge and human attention:** the Run agent button, the agent's own judgements in the log, the approval request, "you corrected" tags.
- **Amber to red is damage.** Never use red for errors in chrome; use text.

Stage background: `radial-gradient(120% 90% at 38% 42%, #12313D 0%, #0B1E26 46%, #061217 100%)`.

## Typography

Load both through `next/font` so they work offline.

| Role | Font | Size and weight |
|---|---|---|
| Loss figure | Big Shoulders Display 900 | `clamp(52px, 6.4vw, 124px)`, line-height 0.9 |
| Gauge numerals | Big Shoulders Display 800 | 30px |
| Gauge level tag, amounts in lists | Big Shoulders Display 800 | 20 to 26px |
| Wordmark | Big Shoulders Display 900 | 26px, letter-spacing 0.06em |
| Panel heading | Hanken Grotesk 600 | 18px |
| Body, log entries | Hanken Grotesk 400 to 600 | 15px, line-height 1.45 |
| Secondary | Hanken Grotesk 400 | 14px |
| Smallest allowed | Hanken Grotesk | 13px, tags only |

Rules:
- Sentence case everywhere. The wordmark and the playbook title are the only capitals.
- No monospace anywhere.
- No tracked-out small labels above headings.
- Numbers that matter are set in the display face; words are set in the body face.
- Round money to three significant figures: `$68.6K`, `$370K`, `$1.19M`. Ranges read "$68.6K to $370K".

## Layout

The flood view is the page. Everything else floats over it.

```
+--------------------------------------------------------------------------+
| WATERLINE  Building E  Industrial, Houston     facts...      [Run agent] |
| +----+                                                    +------------+ |
| | 7  |                                                    | Agent ...  | |
| | 6  |          flood view, full bleed                    |            | |
| | 5  |          (photo-real, dollhouse or 3D model)       |  rail      | |
| | 4  |                                                    |  (glass)   | |
| | 3  |                                                    |            | |
| | 2 <| 2.0 ft                                             |            | |
| | 1  |                                                    |            | |
| +----+                                                    |            | |
| Estimated loss if water reaches 2.0 ft inside             |            | |
| $68.6K to $370K                      key + view switch    +------------+ |
+--------------------------------------------------------------------------+
```

- **Flood view:** fills the viewport behind everything. The Matterport iframe or the 3D canvas is the background layer.
- **Top line:** wordmark, building label, three facts as plain text, Run agent. No bar background.
- **Staff gauge:** left edge, 28px in, from 84px below the top down to the loss block. 64px wide board.
- **Loss block:** bottom left, under the gauge.
- **Key and view switch:** bottom, just left of the rail.
- **Rail:** right, 20px in, width `clamp(340px, 29vw, 440px)`, glass. Tabs: Agent, Assets, Fixes, Site, Send.
- There is no left column. Aerial evidence lives in the Site tab. Files are a toggle inside Agent.
- Left-align text. Spacing unit 4px; common steps 8, 12, 16, 20, 28.
- Must hold at 1280x720 and 1920x1080 with no wrapped labels and no clipped text.

## Components

**Staff gauge.** Yellow board, black ticks every half foot (long at each foot), black numerals 1 to 7. The part below the water level is covered in `rgba(9,84,116,.9)` with a 3px cyan top edge. A cyan tag with a pointer sits at the level and shows the depth, for example "2.0 ft". It is a vertical range input (0 to 8 ft, 0.25 steps): draggable, keyboard operable, with an accessible label. Releasing it during an agent session triggers the re-plan, as the old slider did.

**Loss block.** Line one, muted: "Estimated loss if water reaches 2.0 ft inside". Line two: the central figure in the display face. Line three: its 80% range. Then Contents and Structure with their ranges (moved to "How this number is built" when the screen is short), "Scanned area only. Values are assumed ranges." and a link to how the number is built.

**Asset markers.** Rings, 18px across with a 4px stroke, the same size at any zoom. Stroke colour by damage: dry, partly damaged, lost. Lost rings are filled. Only the selected marker shows a label: name and state on a dark chip. Never spheres or blobs.

**Flood view overlays.** Only the view switch, the key, and loading or fallback notices. No debug text (shared points, RMS, marker counts, scan ids). Floor-level calibration lives behind a small settings control.

**Rail.** Glass panel, 6px radius, 1px hairline border. Tabs are plain words with a 3px cyan underline on the selected one.

**Agent log.** A vertical line with a dot per entry. Each entry: who (13px muted), what (600 weight, one sentence), why (14px muted, optional). The agent's own judgements (layer disagreements, memory applied or skipped, re-plans) get a yellow dot with a soft halo and a yellow "who". Steps answered from cache say so in the "why" line. The approval request is a solid yellow card with black text and two buttons: "Approve and send", "Reject".

**List rows (Assets, Fixes, Site).** Name in 600 weight, one muted line under it, amount right-aligned in the display face, a 5px damage bar under asset rows running amber to red. Tags are small outlined words: "measured", "estimated", and in yellow "you corrected". Vehicles sit in a collapsed group at the bottom of Assets.

**Buttons.** Primary: yellow fill, black text, 3px radius, 700 weight. Secondary: 2px inset outline in the current text colour. One primary button per view.

**Documents (report, playbook).** Shown on a light sheet (`#F4F6F5`, text `#11161A`) inside the rail, with a display-face title. Markdown files are rendered, never shown raw.

**3D model fallback.** A cutaway seen from above at an isometric angle, on a dark plinth, lit, with the ceiling removed. Water is a translucent volume clipped to the building footprint, with a bright edge on its surface and darker visible sides. See the scene in the reference.

## Elevation

- The gauge board casts one soft shadow: `0 18px 40px rgba(0,0,0,.45)`.
- Glass panels have no shadow; the blur and hairline separate them.
- No glows, no gradients on controls, no drop shadows on cards.
- Corners: 3px on controls, 6px on the rail, 0 on the flood view.

## Motion

- One opening move when a building loads: the water rises from 0 to the starting depth over about 1.5 seconds and the loss figure climbs with it.
- Log entries fade up as they arrive.
- The water and figures follow the gauge instantly while dragging.
- Nothing else animates. Respect `prefers-reduced-motion`.

## Words

- Say what things are in plain language: "Outside FEMA's 1% flood zone", "49 of 49 scan positions read", "1 correction remembered".
- Buildings are "Building E", with the type and city after. Street addresses stay hidden unless `NEXT_PUBLIC_SHOW_ADDRESSES=1`.
- Button labels say what happens: "Run agent", "Approve and send", "Reject", "Reset demo".
- States: "Agent running", "Waiting for you", "Sent to <address>", "Draft only, not sent", "Replay of the run recorded at <time>".
- Empty and error states say what to do next: "No recording for this building. Run the agent live." "Photo-real view unavailable. Showing the 3D model. Retry."

## Do

- Keep the flood view as large as the screen allows.
- Keep the gauge yellow and the water cyan, always.
- Always show the central figure together with its 80% range.
- Keep "scanned area only" and "assumed ranges" beside the loss figure.

## Do not

- No left sidebar, no three-column dashboard.
- No monospace, no all-capital labels, no numbered section markers.
- No debug or developer wording on screen (mesh, RMS, SDK, API, server-ranked, backend, artifact).
- No new accent colours, no purple, no neon glow.
- No large sphere markers.
- No raw markdown, no unstyled iframes.
- No text under 13px.

## Landing page

Same stage, type and colours. A real dark basemap when online, the plain grid offline. Markers sized by loss, yellow ring when the building is outside the 1% flood zone and cyan when inside. One sentence computed from the data, set large: for example "5 of 8 buildings sit outside FEMA's 1% flood zone." A compact ranked list of all eight in a glass rail; clicking a row opens the building.
