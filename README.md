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
.venv/bin/python -m app.survey.interior building-h    # vision survey of one building (Gemini)
.venv/bin/python -m app.loss.rank                # precompute loss at 1, 2, 4 ft for the triage map
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

.venv/bin/python -m pytest -q                    # tests
```

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

`.env`, `data/toolkit/` and `data/cache/` are git-ignored. CoStar, Matterport and Vexcel data are proprietary and are never committed.
