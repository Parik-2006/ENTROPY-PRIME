# Entropy Prime — Technology Stack

## Frontend

| Technology | Role |
|-----------|------|
| **React 18** | Single-page UI (Entropy Bank product surface + Deception Demo Lab) |
| **Vite** | Dev server (port 3001) with API proxy, and production bundler |
| **JavaScript (ESM)** | Application language for components, contexts and services |
| **React Router** | Client-side routing and route guards (`PrivateRoute`/`PublicRoute`) |
| **Framer Motion** | Trust modal / banner and page transitions |
| **TensorFlow.js** | In-browser behavioural models (1-D CNN humanity scorer, autoencoder) |

Key frontend modules: `services/biometrics.js` (capture + scoring), `context/
AuthContext.jsx` (session + heartbeat), `context/TrustContext.jsx` (confidence
zones), `services/api.js` and `services/deception.js` (HTTP clients).

## Backend

| Technology | Role |
|-----------|------|
| **FastAPI** | Async HTTP API (`/score`, `/auth/*`, `/session/verify`, `/api/shadow/*`) |
| **Python 3** | Backend language |
| **Uvicorn** | ASGI server (port 8000) |
| **Pydantic** | Request/response validation and typed contracts |
| **NumPy** | Numeric routines for the MAB and pipeline models |

Key backend packages: `backend/main.py` (API + lifespan), `backend/pipeline/`
(four-stage orchestrator + contracts), `backend/models/` (MAB, stage logic),
`framework/deception/` (classifier, synthetic success, shadow world, threat
intel, anti-fingerprint).

## Database & Cache

| Technology | Role |
|-----------|------|
| **MongoDB** (motor) | Durable storage: users, sessions, biometric profiles, honeypot/shadow records |
| **mongomock-motor** | In-memory fallback when MongoDB is unreachable (dev/demo) |
| **Redis** | Session cache and rate limiting (graceful fallback if absent) |

Collections: `users`, `sessions`, `biometric_profiles`, `honeypot`,
`shadow_sessions`, `attacker_events`.

## Security

| Technology | Role |
|-----------|------|
| **Argon2id** (argon2-cffi) | Password hashing with tunable memory/time/parallelism presets |
| **HMAC-SHA256** | Session tokens and signed deception challenges |
| **Server-side session state** | Authoritative session validation via `X-Session-Token` |

## Infrastructure

| Technology | Role |
|-----------|------|
| **Docker / docker-compose** | Containerised backend, MongoDB, Redis, nginx |
| **nginx** | Reverse proxy / static serving in containerised deployments |

## Machine Learning / Behavioural

| Technology | Role |
|-----------|------|
| **Behavioural profiling** | 8-dimensional keystroke/pointer features; frozen-template identity scoring |
| **1-D CNN (TF.js)** | Humanity (human-vs-bot) score from the behavioural window |
| **Autoencoder (TF.js)** | Reconstruction-error drift signal for the watchdog |
| **Multi-Armed Bandit (UCB1)** | Deception-strategy (arm) selection in Stage 2 |
| **Rule-based classifier** | Attacker-intent classification (deterministic, explainable) |

> Note: Stage-3/4 reinforcement-learning agents (DQN/PPO) exist in the codebase
> as scaffolding; the delivered demo relies on the behavioural scorer, the MAB,
> and the rule-based classifier.
