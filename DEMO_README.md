# Entropy Prime — Phase 2 Demo Guide

Short, simple, end-to-end explanation of what the project does, how it is deployed with Docker, and what each component/endpoints do. Includes diagrams and a demo checklist so you can present the prototype clearly.

---

## Abstract (one paragraph)

Entropy Prime is a prototype “zero-trust” authentication demo that augments normal email/password login with behavioral biometrics (keystroke/pointer signals). The frontend (SPA) collects biometric signals while the user types, then calls the backend API to authenticate and to submit biometric data to a 4-stage inference pipeline. The app runs as a Docker Compose stack: `nginx` serves the SPA and reverse-proxies API calls to the FastAPI backend, which stores users and sessions in MongoDB and uses Redis for caching/rate-limits. The backend references trained model checkpoints from the `checkpoints/` folder to run inference.

---

## High-level architecture

```mermaid
graph LR
  Browser[Browser (User)] -->|HTTP(S)| NGINX[nginx reverse proxy]
  NGINX -->|serves| Frontend[Static site (Vite build)]
  NGINX -->|proxies /auth, /score, /api| Backend[FastAPI backend]
  Backend --> Mongo[MongoDB (users, sessions, honeypot)]
  Backend --> Redis[Redis (rate-limit, cache)]
  Backend --> Checkpoints[Model checkpoints (files)]
  Frontend --> SDK[public/sdk/entropy.js]
  Browser -->|keystroke data| Frontend
  Frontend -->|POST /auth/login, /score| NGINX
```

This diagram shows the user (browser) talking to `nginx` which either serves static frontend files or proxies API requests to the backend. The backend reads/writes Mongo and uses Redis for short-lived state. Model files are read from `checkpoints/`.

---

## Login + Scoring sequence (simple steps)

```mermaid
sequenceDiagram
  participant U as User/Browser
  participant FE as Frontend (React/Vite)
  participant NG as nginx
  participant BE as Backend (FastAPI)
  participant DB as MongoDB
  participant RD as Redis

  U->>FE: Open /login (index.html + JS)
  U->>FE: Type email + password (keystrokes recorded)
  FE->>NG: POST /auth/login {email, plain_password}
  NG->>BE: proxy POST /auth/login
  BE->>DB: lookup user, verify password
  DB-->>BE: user document (or not found)
  BE-->>NG: 200 (success) or 401 (invalid)
  NG-->>FE: 200/401
  alt login success
    FE->>NG: POST /score {biometrics, latent_vector}
    NG->>BE: proxy POST /score
    BE->>BE: Stage1 -> Stage2 -> Stage3 -> Stage4
    BE->>DB: create session document
    BE-->>NG: PipelineOutput {session_token, scores, action_label}
    NG-->>FE: PipelineOutput
    FE: store token, update UI
  end
```

---

## What Docker does here (each service)

- `nginx` (container): serves the built SPA (`index.html`, JS/CSS) and reverse-proxies API routes (`/auth/`, `/score`, `/api/`, `/password/`, `/session/`, etc.) to the backend. Also applies caching and rate-limiting. Config: `nginx/nginx.conf`.
- `backend` (container): runs the FastAPI application (handlers + 4-stage inference pipeline). Reads model checkpoints from `checkpoints/` and connects to MongoDB & Redis. Dockerfile builds a production image that bundles static assets into the backend image.
- `mongodb` (container): persistent store for users, sessions, honeypot logs, and admin data. Configured in `docker-compose.yml` and initialized using `mongo/init.js` if present.
- `redis` (container): lightweight cache and rate-limit store, used by nginx/backends for short-lived state.
- Composer: `docker-compose.yml` wires the services, environment variables, healthchecks and networks. Use `docker compose up -d --build` to run the whole stack.

---

## What `nginx` does (details)

- Serves static files from `/usr/share/nginx/html` (the Vite build), so the browser can load the SPA with the same origin as the API.
- Proxies API paths to the backend. This allows the frontend to use relative URLs (no CORS problems).
- Applies rate-limits and caching rules for static assets in `nginx/nginx.conf`.

Common nginx gotchas:
- If a proxied API path is not configured (missing `location` block), the SPA catch-all may return `index.html` for that API URL. That causes JSON parse errors and HTTP 405/HTML responses. Ensure API locations exist for `/score`, `/auth/`, `/password/`, `/session/`, etc.

---

## What MongoDB does (details)

- Stores `users` collection with fields like `email`, `password_hash`, `is_active`.
- Stores `sessions` collection: `session_token`, `user_id`, `latent_vector`, `expires_at`.
- Stores honeypot and audit logs used by the pipeline and admin dashboard.
- Connection is configured via `MONGODB_URL` / `MONGO_PASSWORD` environment variables in `docker-compose.yml` or your local `.env`/`all.env`.

---

## Important endpoints (what they do)

- `POST /auth/register` — Register a new user. Body: `{ email, plain_password }`. Creates user document and returns 201.
- `POST /auth/login` — Login. Body: `{ email, plain_password }`. Verifies argon2 hash; on success creates a session and returns `{ session_token, user_id, email }`.
- `POST /auth/logout` — Invalidate a session token.
- `POST /score` — Submit biometric payload to the 4-stage pipeline. Body: biometric features, latent vector, user agent, server_load. Returns `PipelineOutput` containing `session_token`, `humanity_score`, `entropy_score`, `action_label`, and per-stage metadata.
- `POST /password/hash` — Compute a hash using chosen Argon2 params (used by UI to show or test hashing results).
- `POST /password/verify` — Verify a plain password against a stored hash.
- `POST /session/verify` — Watchdog heartbeat for session verification.
- `POST /telemetry` — Collects events/telemetry (used for analytics).
- `GET /health` — Health check (used by docker-compose healthchecks).
- Admin endpoints: `/admin/*` and `/admin/models-status` — require admin keys; return model / pipeline debug info.

For code: main handlers live in `backend/main.py` and pipeline orchestration in `backend/models/orchestrator.py`.

---

## 4-stage pipeline (plain words)

1. Stage 1 — Biometric extraction: raw keystroke and pointer signals are normalized and converted into features (theta, h_exp, latent_vector).
2. Stage 2 — Honeypot: classifier decides whether to shadow the user or route them to a synthetic challenge (and selects a MAB arm when shadowing).
3. Stage 3 — Governor (DQN + PPO): determines Argon2 hashing parameters (memory/time/parallelism) and may select behavioral actions (e.g., stricter reauth flows).
4. Stage 4 — Watchdog: continuous checks for identity drift and recommends actions (ok, passive_reauth, disable_sensitive_apis, force_logout).

The orchestrator composes these results into the `PipelineOutput` returned by `/score`.

---

## Demo checklist (commands and steps)

1. Make sure local envs are set (copy `.env.example` → `.env` or populate `all.env`):

```powershell
# Example (PowerShell)
set -Machine EP_SESSION_SECRET=replace_with_secure_value
set -Machine MONGO_PASSWORD=your_mongo_pass
set -Machine REDIS_PASSWORD=your_redis_pass
```

2. Start Docker Compose (from repo root):

```bash
docker compose up -d --build
```

3. Verify containers and logs:

```bash
docker ps --filter "name=entropy_"
docker logs entropy_backend --tail 200
docker logs entropy_nginx --tail 200
```

4. Open the demo:

 - Visit `http://localhost/login` in a browser.
 - Register a test user and log in.
 - Observe backend logs showing `Registered` and `Login` messages and `/score` pipeline logs.

5. If you see JSON parse errors in the frontend, verify nginx returned JSON (not HTML). Check `nginx` logs to ensure requests are proxied rather than served by the SPA catch-all.

---

## Troubleshooting quick reference

- 405 / HTML returned: nginx is routing to SPA. Fix: add `location` block for the API route in `nginx/nginx.conf` and reload nginx (rebuild container).
- 500 with PPO/DQN matrix errors: model checkpoint mismatch or missing checkpoint — confirm files in `checkpoints/` and correct `EP_*_CHECKPOINT` env vars.
- Mongo auth failures: check `MONGO_PASSWORD` and the `MONGODB_URL` used by the container.

---

## Where to read code (quick pointers)

- `backend/main.py` — API handlers and app startup
- `backend/models/orchestrator.py` — pipeline orchestration (Stage 1→4 aggregation)
- `backend/models/*.py` — per-stage logic (see `stage1_biometric.py`, `stage2_honeypot.py`, `stage3_governor.py`, `stage4_watchdog.py`)
- `src/pages/LoginPage.jsx` — login UI flow and orchestration of login → score
- `src/services/api.js` — frontend HTTP client wrapper and endpoints
- `nginx/nginx.conf` — static serving + proxy rules
- `docker-compose.yml` — service definitions and env wiring

---

If you want I will:

- produce a single-slide markdown (or PDF) summary with these diagrams for your presentation, or
- create a short automated smoke-test script that performs register → login → score and prints the responses.

Tell me which one you prefer and I'll add it to the repo.
