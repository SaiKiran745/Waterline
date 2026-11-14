# Waterline frontend

## Run

Start the backend at `http://localhost:8000`. In the repository-root `.env`, set `NEXT_PUBLIC_MATTERPORT_SDK_KEY` to a browser SDK key authorized for `localhost:3000`. API mode is the default; `WATERLINE_DATA_SOURCE=fixture` is available only for fixture development.

Then run from `frontend/`:

```bash
npm install
npm run bundle:download
set -a; source ../.env; set +a
npm run dev
```

Open `http://localhost:3000`. The `set -a` step exports the root `.env` into Next.js. `bundle:download` fetches Matterport Bundle SDK `26.5.4_webgl-708-g332adb66f5` from Matterport's official distribution into the git-ignored `public/matterport-bundle/`; licensed bundle files are never committed.

The photo-real view requires WebGL plus network access to Matterport. If the bundle, network, WebGL, or viewer connection fails, the app visibly falls back to the local OBJ-based 3D model view; the room safety view remains available as a second fallback.
