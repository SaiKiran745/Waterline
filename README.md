# Waterline

Flood maps stop at the front door. Waterline takes the water inside.

Waterline is an AI agent for commercial buildings in Houston. It finds where flood water gets in from Vexcel aerial imagery, inventories what a flood would damage from the building's Matterport scan, prices the loss with CoStar building data, and ranks fixes. Built for HackPrinceton Fall 2026, CoStar track.

- Brief for coding agents: `AGENTS.md` (copied to `CLAUDE.md`)
- Data shapes (frozen): `contracts/README.md`
- What each data source offers: `docs/DATA_NOTES.md`
- Decisions and the building shortlist (by letter): `docs/DECISIONS.md`

## Backend

Needs Python 3.11 or newer, the sponsor toolkit in `data/toolkit/`, and keys in `.env` (see `.env.example`).

```bash
cd backend
python3.14 -m venv .venv                         # any Python 3.11+
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m app.sources.shortlist        # pick the shortlist -> data/cache/shortlist.json
.venv/bin/python -m app.sources.pull             # pull and cache every layer for it (about 2 GB)
.venv/bin/python -m app.loss.build_curves        # Hazus 6.1 structure curves -> app/loss/curves.yaml
.venv/bin/python -m app.survey.calibrate building-h   # measure the panorama face convention (already recorded)
.venv/bin/python -m app.survey.scout                  # contents scout: 3 positions per building -> data/cache/scout.json
.venv/bin/python -m app.survey.interior building-e    # vision survey of one building (Gemini; --cached-positions-only to rebuild)
.venv/bin/python -m app.survey.spotcheck building-e   # 10-asset spot-check table (--sheet out.jpg for a local review sheet)
.venv/bin/python -m app.loss.rank                # precompute loss at 1, 2, 4 ft for the triage map
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

.venv/bin/python -m pytest -q                    # tests
```

### Run the backend for the front end

Keep this running in its own terminal while the front end is up:

```bash
cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- The front end calls `http://localhost:8000` (`WATERLINE_DATA_SOURCE=api` in `frontend/.env.local`, the default).
- CORS allows `http://localhost:3000`.
- `/media` answers only to requests from this machine.
- To keep it running after the terminal closes:

```bash
cd backend && nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 > ../data/cache/uvicorn.log 2>&1 &
```

- To stop it: `kill $(lsof -tiTCP:8000 -sTCP:LISTEN)`.
- Add `DEMO_MODE=1` in front of either command to serve strictly from cache.

`DEMO_MODE=1` (in `.env` or the environment) makes the backend read only from `data/cache/` and fail loudly on a miss: `DEMO_MODE=1 .venv/bin/python -m app.sources.pull` checks that the cache is complete.

### API

All responses follow `contracts/`. CORS allows `http://localhost:3000`.

| Endpoint | Returns |
|---|---|
| `GET /buildings` | Building list, ranked by precomputed loss at 2 ft. `?fixture=1` returns the FIXTURE building |
| `GET /buildings/{id}` | `{"building", "entry_points", "assets"}`; ids are slugs such as `building-h` |
| `GET /buildings/{id}/scenario?depth_ft=` | ScenarioResult at any depth from 0 to 8 ft |
| `GET /buildings/{id}/mitigations?depth_ft=` | Mitigations ranked at exactly that depth; ids are stable across depths |
| `GET /buildings/{id}/media` | Media manifest: mesh, aerial images, and panorama faces cleared by the privacy screen |
| `PATCH /buildings/{id}/assets/{asset_id}?depth_ft=` | Human correction: any of `label`, `category`, `height_ft_low`, `height_ft_high`, `room`, plus an optional `note`. Saved, applied on every read, written to the agent's memory. Returns `{correction, asset, similar_asset_ids, scenario, mitigations}` |
| `DELETE /buildings/{id}/assets/{asset_id}?depth_ft=` | Removes a wrong asset (optional body `{"note"}`). Returns the same shape, with `asset: null` |
| `GET /triage?depth_ft=1\|2\|4` | Every building ranked by total loss, labelled `surveyed` (with positions read and contents count) or `structure only`. Not in `contracts/` yet |
| `POST /buildings/{id}/run` | Starts the agent (fixture: trace replay) |
| `GET /buildings/{id}/events?speed=` | SSE stream of AgentEvent (`event: agent_event`, then `event: end`) |
| `GET /buildings/{id}/report?depth_ft=`, `/playbook?depth_ft=` | HTML |
| `POST /buildings/{id}/send` | Needs `{"approved": true, "recipient": "<in ALLOWED_RECIPIENTS>"}`; nothing is sent before Phase 5B |
| `GET /media/{id}/manifest.json` | Same manifest (localhost only) |
| `GET /media/{id}/...` | The cached files themselves (localhost only). Panorama faces are served only when the privacy screen cleared them |

The building `fixture-1` (FIXTURE, not real data) supports every endpoint. For real buildings, `run` and `events` answer 501 until the live agent exists (Phase 5).

## Frontend

Next.js, in `frontend/` (workstream B).

## Data and secrets

Gemini spend is logged per call in `data/cache/spend.json`. A call that could take the total past `GEMINI_BUDGET_USD` (default 3) is refused before it is made, and HTTP 402 (credits depleted) stops a survey.

`.env`, `data/toolkit/` and `data/cache/` are git-ignored. CoStar, Matterport and Vexcel data are proprietary and are never committed.
