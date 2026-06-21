# Build Verification

> Run after the deployment fixes. Re-run before each deploy.

## Frontend (Vite)
```
npm run build
```
Result: **PASS** — `✓ built in ~14s`, output to `dist/`. Bundles emitted:
`index.html`, `assets/index-*.css`, `assets/react-*.js`, `assets/index-*.js`,
`assets/tensorflow-*.js`. (The >500 kB chunk warning is the pre-existing TensorFlow.js
bundle — expected, not an error.)

## Backend (Python syntax)
```
.venv/Scripts/python.exe -m py_compile \
  backend/main.py backend/database.py \
  backend/services/redis_client.py backend/services/biometric_compare.py
```
Result: **PASS** — `PY_COMPILE_OK` (all changed modules compile).

> Full import (`uvicorn backend.main:app`) additionally requires the backend deps
> (torch, motor, argon2, …). Verify that on Render during the build step; locally it
> requires the backend venv with `requirements.txt` installed. See `RENDER_SETUP.md`
> for the PyTorch build caveat.

## What changed (deployment fixes only)
- `backend/database.py` — accept `MONGODB_URI` (fallback `MONGODB_URL`).
- `backend/services/redis_client.py` — accept `REDIS_URL`/`REDIS_URI` (fallback `EP_REDIS_URL`).
- `backend/main.py` — CORS `allow_origin_regex` for `*.vercel.app`.
- `src/services/api.js` — `VITE_API_BASE_URL`/`VITE_BACKEND_URL` support.
- `src/sdk/index.js` — env-driven default endpoint.
- `vercel.json`, `render.yaml`, `.gitignore`, `.env.example` — added/updated.

## Behavior preserved
All defaults/fallbacks retained, so local dev and existing behavior are unchanged;
no biometric / PPO / watchdog / trust / honeypot / threat-intel / Phase A–D logic was
modified, and no collections/routes/APIs were removed.
