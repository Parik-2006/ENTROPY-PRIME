# Entropy Prime — Framework Architecture

> Status: Phases 0–5 complete (facade + API gateway + SDKs + examples).
> Restructuring is **additive**: the only pre-existing file modified is
> `backend/main.py` (+20 lines, a guarded `/v1` mount at the end). Everything
> else is new. See `MIGRATION_LOG.md` for the full change ledger.

Entropy Prime is a **behavioral security framework** — a product that
applications consume (like reCAPTCHA / Turnstile / Auth0), not a website. It
answers one question continuously: *"Is this still the same human?"* — even when
the account, browser, laptop, and IP are identical.

---

## 1. Layered architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│ APPLICATIONS   web app · banking · SaaS · e-commerce · mobile (future)     │
└───────────────┬───────────────────────────────────────┬────────────────────┘
                │ JavaScript SDK                         │ Python SDK
                │ framework/sdk/js                       │ framework/sdk/python
                ▼                                         ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ API GATEWAY    framework.api_gateway  →  /v1/* (versioned, resource routers)│
│                mirrors backend/main.py handlers; same logic, /v1 prefix     │
└───────────────┬────────────────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR   framework.orchestrator (EngineSequencer)                     │
│                fail-safe: degrade, never crash                              │
└───┬───────────────┬────────────────┬──────────────────┬────────────────────┘
    ▼               ▼                ▼                  ▼
┌─────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
│ PHASE 1 │  │   PHASE 3    │  │   PHASE 2    │  │      PHASE 4         │
│ Cadence │  │  Honeypot    │  │     DMS      │  │  Continuous Auth     │
│ Engine  │  │   Engine     │  │   Engine     │  │      Engine          │
└────┬────┘  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘
     └──────────────┴── framework.shared (contracts/enums/thresholds) ──┘
                                  │
┌──────────────────── framework.intelligence_engine ────────────────────────┐
│ cross-site threat intel · notifications · outgoing signed webhooks         │
└────────────────────────────────────────────────────────────────────────────┘
                                  ▼
┌──────────────────────────── framework.storage ────────────────────────────┐
│ MongoDB (users/sessions/biometric_profiles/honeypot/threats) · Redis cache │
└────────────────────────────────────────────────────────────────────────────┘
```

### The facade principle (why nothing broke)
Every `framework.*` engine **re-exports** the canonical implementation that
already lives under `backend/`. No business logic was copied or forked. The
running app (`uvicorn main:app`) is unchanged; `framework/` is a new public
surface layered on top. Verified by object-identity asserts: e.g.
`framework.honeypot_engine.MABAgent is backend.models.mab.MABAgent`.

---

## 2. The four engines (phases)

### Phase 1 — Cognitive Cadence Engine  (`framework.cadence_engine`)
Human vs bot from behavioral biometrics.
- **In**: dwell/flight times, keystroke dynamics, mouse velocity/acceleration,
  scroll, cursor path (captured browser-side).
- **Out**: humanity score θ ∈ [0,1], verdict (bot/suspect/human), confidence,
  32-dim embedding.
- **Models**: `CNN1D` (`backend/models/cnn1d.py`); browser 1D-CNN
  (`src/services/biometrics.js`).
- **Source**: `backend/pipeline/stage1_biometric.py`, `backend/services/biometric_services.py`.

### Phase 2 — Dynamic Memory Security  (`framework.dms_engine`)
Adaptive Argon2id hardening — shift compute cost onto attackers (asymmetric
defense). Weak password / low trust → heavier cost; strong / trusted → lighter.
- **In**: expectation entropy (Hexp), Zipf pattern, server load, biometric verdict.
- **Out**: `GovernorResult` (preset, memory_kb, time_cost, parallelism, action).
- **Models**: `DQNAgent` (preset 0–3) + `PPOPolicyAgent` (ALLOW/LOG/CHALLENGE/BLOCK).
- **Source**: `backend/models/stage3_governor.py`, `backend/models/{dqn,ppo_agents}.py`.

### Phase 3 — Generative Honeypot Engine  (`framework.honeypot_engine`)
Deception instead of blocking. Confirmed bots are shadow-routed and served
signed, invisible DOM decoys; a Multi-Armed Bandit learns the best strategy.
- **Arm map**: 0 Tarpit (brute force), 1 Echo (credential stuffing), 2 Canary
  (scraping/crawlers); Shadow-Admin (recon) planned.
- **Out**: `HoneypotResult` (should_shadow, synthetic_token, MAB arm, signed
  `ChallengeConfig`).
- **Models**: `MABAgent` UCB1 (`backend/models/mab.py`); UI in `frontend/honeypot-ui/`.
- **Source**: `backend/models/stage2_honeypot.py`.

### Phase 4 — Continuous Authentication Engine  (`framework.continuous_auth_engine`)
Identity-drift detection tolerant of human variability (relative drift vs an
adaptive baseline, not absolute speed).
- **Zones**: GREEN (ok) · YELLOW (passive_reauth / disable_sensitive_api) ·
  RED (force_logout, only when profile is `stable`).
- **In**: 32-dim latent vector, autoencoder reconstruction error (e_rec),
  DB-sourced trust, adaptive threshold.
- **Models**: `PPOAgent` actor-critic (`backend/models/ppo.py`) + autoencoder
  (`src/services/biometrics.js`).
- **Source**: `backend/pipeline/stage4_watchdog.py`, `backend/services/watchdog_services.py`.

> **Critical invariant** (preserved): the governor uses `PPOPolicyAgent`
> (`select_action → int`); the watchdog uses `PPOAgent` (`select_action →
> (int, float)`). Swapping them reintroduces the historical "BUG-A" TypeError.

---

## 3. Request flows

### Login / score
```
SDK collects behavior → POST /v1/score
  → orchestrator.run(BiometricInput)
      → Cadence (verdict/θ)
      → Honeypot (bot? → shadow token + ECONOMY, skip DMS/CA)
      → DMS (Argon2id preset + action)
      → Continuous-Auth (drift/trust)
  → PipelineOutput {session_token, shadow_mode, argon2_params, action_label, watchdog}
```

### Continuous heartbeat
```
SDK every ~30s → POST /v1/session/verify
  → DB-authoritative onboarding gate (drift suppressed until `stable`)
  → Continuous-Auth → action ok|passive_reauth|disable_sensitive_api|force_logout
  → persists trust; logs drift; cross-site threat ingest
```

### Transaction gate
```
App before a sensitive action → POST /v1/session/trust
  → combine DB trust + client signal + transaction risk
  → allow | challenge | deny
```

---

## 4. API surface

The framework exposes a versioned `/v1` API mirroring the legacy routes 1:1
(46 routes), grouped into resource routers:

| Router | Concern |
|---|---|
| `auth` | register / login / logout / me |
| `score` | full pipeline, telemetry, adaptive password hashing |
| `session` | continuous-auth heartbeat + trust gate |
| `biometric` | profile-build state machine + Stage-1 analytics |
| `honeypot` | MAB reward, decoy trigger, signatures |
| `admin` | model status, onboarding summary, pipeline debug, dashboards |
| `integration` | webhooks + notifications |
| `health` | liveness |

Both `/score` (legacy) and `/v1/score` (framework) are served and resolve to the
same handler. Legacy routes are never removed.

---

## 5. SDKs

- **JavaScript** (`framework/sdk/js`): browser, fetch-based, zero deps. Captures
  behavior, `flush()` → `/v1/score`. Production swaps in the tfjs engine via
  `setEngine()`.
- **Python** (`framework/sdk/python`): stdlib-only REST client for server-to-
  server use: `enroll/login/score/verify/trust/honeypot_reward`.

---

## 6. Data & privacy

Raw keystrokes/mouse never leave the browser. Only θ, a 32-float latent vector,
and aggregated EMA stats are transmitted. MongoDB stores aggregated statistics
only. Onboarding state machine (`collecting → syncing → stable → drifted`) is
server-authoritative.

---

## 7. Deployment (current; Docker reorg is Phase 6, not yet done)

Unchanged from before this restructuring:
- `uvicorn main:app` (FastAPI, 4 workers in prod)
- Nginx TLS + static SPA, MongoDB 7, Redis 7 via `docker-compose.yml`
- Graceful degradation: no Mongo → in-memory mongomock (dev/test); no Redis →
  session cache falls back to DB, rate-limiting allows.

---

## 8. Roadmap (paused, awaiting approval)
- **Phase 6**: Docker reorg into `deploy/`, split-ready engine containers,
  remove published datastore host ports.
- **Phase 7**: physically relocate verified duplicates (root `*.tsx`,
  `new files/`, `main_redis_patch.py`) into `legacy/`.
- **Security track** (separate): gate admin/integration endpoints, rotate the
  committed JWT key, fix CORS — delivered independently, not bundled here.
