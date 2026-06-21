# Deployment Audit (Production Readiness)

> Audit of the repo for Vercel (frontend) + Render (backend) + MongoDB Atlas +
> Upstash Redis. Fixes applied in the same commit are marked **FIXED**.

## Targets
- Frontend: **Vercel** (Vite SPA, output `dist/`)
- Backend: **Render** → `https://entropy-prime.onrender.com`
- DB: **MongoDB Atlas**, database `entropy_prime`
- Cache: **Upstash Redis** (`rediss://` URL)

## Inspected
`package.json`, `vite.config.js`, `backend/requirements.txt`, `backend/main.py`
(entrypoint, CORS), `backend/database.py` (Mongo), `backend/services/redis_client.py`
(Redis), `src/services/api.js` (fetch client), `src/sdk/index.js`, `.gitignore`,
`.env` / `.env.example`, startup scripts.

## Findings & fixes

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | Frontend client read only `VITE_API_URL`; defaulted to `''` (same-origin) in browser → prod would call Vercel, not the backend | High | **FIXED** — `src/services/api.js` now prefers `VITE_API_BASE_URL`→`VITE_BACKEND_URL`→`VITE_API_URL` |
| 2 | Backend Mongo read only `MONGODB_URL`; deployment standard is `MONGODB_URI` | High | **FIXED** — `database.py` accepts `MONGODB_URI` or `MONGODB_URL` |
| 3 | Redis read **only** `EP_REDIS_URL`; `REDIS_URL`/`REDIS_URI` were ignored → Upstash never used | High | **FIXED** — `redis_client.py` accepts `EP_REDIS_URL`/`REDIS_URL`/`REDIS_URI` |
| 4 | CORS allow-list had no `*.vercel.app` support | High | **FIXED** — added `allow_origin_regex` (`CORS_ORIGIN_REGEX`, default `https://.*\.vercel\.app`) |
| 5 | No `vercel.json` / `render.yaml` | Med | **FIXED** — both created (SPA rewrites; Render web service) |
| 6 | `.env.example` lacked deployment vars | Med | **FIXED** — rewritten with all required names, no secrets |
| 7 | `.gitignore` missing `.env.development`, `backend/.env`, `frontend/.env` | Med | **FIXED** — deployment block appended; `!.env.example` preserved |
| 8 | `src/sdk/index.js` hardcoded `http://localhost:8000/api/v1` | Low | **FIXED** — env-driven default, localhost only as last-resort dev fallback |
| 9 | `vite.config.js` dev proxy → `localhost:8000` | Info | **OK** — dev-only proxy; not used in the built SPA. Left as-is. |

## Remaining blockers / risks (manual action required)

- **`torch==2.11.0` in `backend/requirements.txt`** — **BLOCKER to verify.** Torch is
  large and this exact version may not publish a wheel for Render's Python. Building
  torch can also exceed memory/time on small Render plans.
  - Action: confirm a valid CPU build (e.g. a published `torch` version) and consider
    `pip install ... --extra-index-url https://download.pytorch.org/whl/cpu`, and/or a
    paid Render instance. Not auto-changed here to avoid pinning an also-wrong version.
- **Secrets were shared in plaintext** (Mongo password, Upstash token). Treat them as
  compromised: **rotate** after deploy. Also note `backend/run-backend.bat` contains a
  local dev password — keep it dev-only; never use those creds in prod.
- **`node_modules` has tracked files** (e.g. `node_modules/.vite/deps/_metadata.json`)
  from a prior commit despite `.gitignore`. Pre-existing; not changed here. Optional
  cleanup later: `git rm -r --cached node_modules`.

## Localhost references after fixes
- `src/services/api.js` → env-driven (localhost only as non-browser fallback). ✅
- `src/sdk/index.js` → env-driven default. ✅
- `vite.config.js` dev proxy → localhost (dev-only, intentional). ✅
- No hardcoded localhost remains in the **built** frontend's API path.

## MongoDB verification (Step 7)
- Code path: `backend/database.py:connect_to_mongo` → `MONGODB_URI`/`MONGODB_URL` +
  `MONGODB_DB_NAME` (default `entropy_prime`).
- All collections preserved and created/used by existing helpers: `users`, `sessions`,
  `biometric_profiles`, **`enrollment_baselines`**, **`biometric_comparisons`**
  (Phase D.1), `drift_events`, `feature_selections`, `honeypot`,
  `threat_intelligence`, `threat_broadcasts`, `tenants`, `sites`. Indexes built in
  `_create_indexes` (idempotent). No collection renamed or removed.
- Atlas note: whitelist Render egress IPs (or `0.0.0.0/0` for demo) in Atlas Network
  Access, and ensure the DB user has readWrite on `entropy_prime`.
