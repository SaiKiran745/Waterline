# Waterline frontend

Run the API at `http://localhost:8000`, then:

```bash
npm install
npm run bundle:download
set -a; source ../.env; set +a
npm run dev
```

`bundle:download` fetches Matterport Bundle SDK `26.5.4_webgl-708-g332adb66f5` from Matterport's official distribution into `public/matterport-bundle/`. That directory is git-ignored because the Bundle SDK is licensed vendor software and must not be committed. Set `NEXT_PUBLIC_MATTERPORT_SDK_KEY` in the repository-root `.env`; the `set -a` step exports that root file into the Next.js process, and the key must allow `localhost:3000`.

If the Bundle is missing or cannot connect, the app automatically returns to the local OBJ-based 3D model view.
