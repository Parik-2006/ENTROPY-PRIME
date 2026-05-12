# ⚡ ENTROPY PRIME — Zero-Trust Behavioral Biometrics Engine

> **Study focus:** this project detects bots with browser-side behavioral signals, then uses those signals to score trust, adjust server cost, and route suspicious sessions.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Build](https://img.shields.io/badge/build-passing-brightgreen)]()
[![SDK](https://img.shields.io/badge/SDK-entropy.min.js-blue)]()

---

## 5-Minute Onboarding

> Follow these four steps to understand the full flow from setup to verification.

### Step 1 — Clone & configure (1 min)

```bash
git clone https://github.com/your-org/entropy-prime.git
cd entropy-prime

# Generate required secrets — do this once
export EP_SESSION_SECRET=$(openssl rand -hex 64)
export EP_SHADOW_SECRET=$(openssl rand -hex 64)
export MONGO_PASSWORD=$(openssl rand -hex 24)
export REDIS_PASSWORD=$(openssl rand -hex 24)
```

> **Tip**: Store them in a `.env` file so the same values are reused across local runs and Docker Compose can load them automatically.

```bash
# Save to .env (never commit this file)
cat > .env << EOF
EP_SESSION_SECRET=${EP_SESSION_SECRET}
MONGO_PASSWORD=${MONGO_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
EP_DOMAIN=${EP_DOMAIN}
EOF
```

---

### Step 2 — Start the stack (1 min)

**Local development** (no TLS, hot reload):
```bash
chmod +x start.sh && ./start.sh
# ✓ Backend  → http://localhost:8000
# ✓ Frontend → http://localhost:3000
# ✓ API docs → http://localhost:8000/docs
```

**Windows development** (Docker for MongoDB/Redis, separate backend/frontend windows):
```bash
start.bat
# ✓ MongoDB and Redis run from docker-compose.dev.yml
# ✓ Backend  → http://localhost:8000
# ✓ Frontend → http://localhost:3000
```

**Production** (Docker Compose stack with Nginx, backend, MongoDB, Redis):
```bash
docker-compose up -d --build
# ✓ Uses docker-compose.yml in the repository root
```

Check the backend health endpoint:
```bash
curl http://localhost:8000/health
# {"status":"ok","version":"4.0.0","pipeline":"active","stages":4,"timestamp":...}
```

---

### Step 3 — Add the SDK to your login page (2 min)

**Option A — CDN `<script>` tag** (fastest, no build step):

```html
<!-- Paste before your closing </body> tag -->
<script
  src="https://cdn.yourdomain.com/entropy-prime/entropy.min.js"
  integrity="sha384-<hash-from-dist/sdk-manifest.json>"
  crossorigin="anonymous">
</script>

<script>
  const ep = new EntropyPrime({
    apiUrl: 'https://api.yourdomain.com',
    onScore: (score, label) => {
      console.log(`Humanity score: ${score.toFixed(2)} -> ${label}`);
    },
    onSession: (token) => {
      document.querySelector('#ep-token').value = token;
    }
  });
  ep.attach(document.querySelector('#login-form'));
</script>
```

**Option B — ES module import** (for React / Vue / bundled apps):

```bash
npm install entropy-prime
```

```ts
import { EntropyPrime } from 'entropy-prime';

const ep = new EntropyPrime({ apiUrl: import.meta.env.VITE_API_URL });
ep.attach(formRef.current);
```

The SDK captures keystrokes and mouse movements entirely in the browser, so raw signals never leave the device.

---

### Step 4 — Validate on your backend (1 min)

Attach the session token issued by the SDK to every sensitive API call:

```bash
curl -X POST http://localhost:8000/verify \
  -H "Content-Type: application/json" \
  -d '{"session_token": "<token-from-sdk>"}'

# { "valid": true, "theta": 0.94, "label": "human", "expires_in": 3600 }
```

On your backend, reject requests where `theta < 0.5` or `valid: false`. In the containerized stack, the public health URL is proxied through Nginx at `/health`.

---

## Project Overview

Modern authentication is vulnerable to stolen cookies, replay attacks, and spoofed fingerprints. ENTROPY PRIME shifts trust to browser-observed behavioral signals, then uses those signals to estimate whether the session is likely human.

### Core Algorithmic Phases

| Phase | Where | What happens |
|---|---|---|
| **Biological Gateway** | Browser | Captures dwell/flight times, velocity, and jitter. A 1D-CNN turns them into a humanity score θ in the range [0,1]. |
| **Resource Governor** | Backend | A DQN agent chooses Argon2id cost dynamically: heavier for bots, lighter for trusted users. |
| **Offensive Deception** | Backend | Very low scores (θ < 0.1) are given synthetic tokens and redirected into a honeypot path. |
| **Session Watchdog** | Both | A deep autoencoder keeps a baseline and lowers trust if session behavior changes midstream. |

### Privacy Model

```
Browser (client)                  Server (backend)
───────────────────────────       ────────────────────────
Raw keystrokes      ─╮
Raw mouse coords    ─┤  never      Only transmitted:
Dwell/flight times  ─┤  leave      • θ          (1 float)
Velocity/jitter     ─╯  browser   • H_exp       (1 float)
                                   • latent vec  (32 floats)
                                   • EMA stats   (8 floats, aggregated)
```

Raw biometric signals are processed in-browser. The server only sees compact derived features and aggregated EMA statistics — never raw keystroke sequences or mouse coordinates.

---

## Profile-Build Onboarding State Machine

Every new user passes through a dedicated profile-build phase before drift detection arms. The state is stored in `biometric_profiles.onboarding_state` in MongoDB and is the **single authoritative source of truth** for both the backend drift gate and the frontend UI panels.

### State Diagram

```
  [register / login]
         │
         ▼
   ┌─────────────┐   sample_count < 50        ┌─────────────┐
   │ COLLECTING  │ ─────────────────────────▶ │ COLLECTING  │  (loop)
   └─────────────┘                             └─────────────┘
         │
         │  sample_count >= 50 + sync confirmed
         ▼
   ┌─────────────┐
   │   SYNCING   │  (transient — backend write in progress)
   └─────────────┘
         │
         │  write confirmed
         ▼
   ┌─────────────┐   normal behavior          ┌─────────────┐
   │   STABLE    │ ─────────────────────────▶ │   STABLE    │  (loop)
   └─────────────┘                             └─────────────┘
         │
         │  watchdog: drift > adaptive_threshold
         ▼
   ┌─────────────┐
   │   DRIFTED   │ ◀─── watchdog armed only in STABLE
   └─────────────┘
         │
         │  POST /biometric/profile/reset  OR  fresh login
         ▼
   ┌─────────────┐
   │ COLLECTING  │  (fresh baseline from scratch)
   └─────────────┘
```

### State Rules

| State | Drift Detection | Force-Logout | UI Panel shown |
|---|---|---|---|
| `collecting` | ✗ suppressed | ✗ downgraded to `passive_reauth` | Progress bar |
| `syncing` | ✗ suppressed | ✗ downgraded to `passive_reauth` | Saving spinner |
| `stable` | ✓ armed | ✓ allowed | Demo controls + proceed button |
| `drifted` | n/a | n/a (session already flagged) | Re-auth prompt + reset button |

### Key Design Decisions

**Server is authoritative.** The client passes `onboarding_state` in heartbeat payloads as a hint, but the backend re-reads the value from MongoDB before making any gating decision. A misbehaving client that always sends `collecting` cannot permanently suppress drift detection.

**Sticky drifted rule.** Once a profile transitions to `drifted`, only an explicit reset (`POST /biometric/profile/reset`) or a completed re-auth (login auto-resets drifted profiles) moves it back. The watchdog cannot flip `drifted → stable`.

**No raw data in MongoDB.** The `biometric_profiles` collection stores only EMA means, variances, sample counts, and 8-channel rolling averages. Raw keystrokes, mouse coordinates, and dwell sequences remain in the browser and are discarded after local feature extraction.

**Cold-start isolation.** Onboarding is treated as a dedicated application state, not a mode within the normal session flow. New accounts land on `/profile-build` and are blocked from `/dashboard` until their state transitions to `stable`. Login returns `onboarding_state` so the router can direct the user correctly without an extra round-trip.

**Drifted profiles auto-reset on login.** When a user with a `drifted` profile logs in, the backend automatically calls `reset_biometric_profile` before issuing the session token, so the user always starts profile-build fresh rather than arriving at a broken state.

---

## SDK Reference

### Constructor

```ts
new EntropyPrime(config?: EntropyConfig)
```

| Option | Type | Default | Description |
|---|---|---|---|
| `apiUrl` | `string` | `http://localhost:8000` | Backend base URL |
| `threshold` | `number` | `0.5` | Bot/human decision boundary |
| `debug` | `boolean` | `false` | Verbose console output |
| `heartbeatInterval` | `number` | `30000` | Session keepalive (ms) |
| `onScore` | `function` | — | Called when θ is computed |
| `onSession` | `function` | — | Called when a session token is issued |
| `onError` | `function` | — | Called on network or ML errors |

### Methods

```ts
ep.attach(target?)   // Start capturing events (default: document)
ep.detach()          // Stop capture, cancel heartbeat
ep.flush()           // Force immediate score computation → Promise<ScoreResult>
ep.theta             // Current humanity score (read-only)
ep.sessionToken      // Current session token (read-only, null before first score)
```

### CDN integrity hash

After running `scripts/bundle-sdk.sh`, read `dist/sdk-manifest.json` for the current SRI hash:

```bash
cat dist/sdk-manifest.json | python3 -m json.tool | grep sha384
```

---

## Backend API

### Core pipeline endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Liveness check; returns model load status |
| `POST` | `/score` | — | Accepts θ, H_exp, latent vector; returns session token |
| `POST` | `/session/verify` | Session token | Heartbeat; returns watchdog result + `onboarding_state` + `drift_detection_armed` |
| `POST` | `/honeypot/reward` | — | MAB reward feedback |
| `GET` | `/admin/models-status` | — | Reports CNN/DQN/autoencoder status |

### Profile-build endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/biometric/profile` | ✓ Session | Sync aggregated stats; returns `profile_status` embedding `onboarding_state` |
| `GET` | `/biometric/profile/{user_id}` | ✓ Session (own) | Full profile document |
| `GET` | `/biometric/profile/{user_id}/status` | ✓ Session (own) | Lightweight `ProfileBuildStatus` poll |
| `POST` | `/biometric/profile/reset` | ✓ Session | Wipe EMA → `collecting`; call after re-auth |

### Authentication endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/register` | Register; seeds empty profile in `collecting`; returns `onboarding_state` |
| `POST` | `/auth/login` | Login; returns `onboarding_state`; auto-resets `drifted` profiles to `collecting` |
| `POST` | `/auth/logout` | Invalidate session |
| `GET` | `/me` | Current user profile; includes `onboarding_state` |

### Integration API endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/webhooks/endpoints` | Register a signed delivery endpoint |
| `GET` | `/webhooks/endpoints` | List endpoints (filterable by `customer_id`) |
| `GET` | `/webhooks/endpoints/{id}` | Fetch one endpoint |
| `PATCH` | `/webhooks/endpoints/{id}` | Update url / secret / events / enabled |
| `DELETE` | `/webhooks/endpoints/{id}` | Unregister endpoint |
| `POST` | `/webhooks/endpoints/{id}/test` | Send a test delivery |
| `POST` | `/session/trust` | Gate check before a sensitive transaction |
| `GET` | `/session/trust/{session_id}` | Poll current trust posture |
| `GET` | `/notifications` | Query notification log |
| `GET` | `/notifications/stats` | Aggregated event counts |
| `POST` | `/notifications/thresholds` | Per-customer alert threshold config |
| `GET` | `/notifications/thresholds/{id}` | Read per-customer thresholds |

### Admin endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/admin/onboarding-summary?tenant_id=` | Per-tenant count of users in each onboarding state |
| `GET` | `/admin/pipeline-debug` | Run pipeline with synthetic input; inspect all stage outputs |
| `GET` | `/admin/honeypot/dashboard` | Recent honeypot signatures |

Full interactive docs: `http://localhost:8000/docs`

---

## Data Contract: `biometric_profiles` Collection

Only aggregated statistics are stored. Raw keystroke sequences and mouse coordinates are never written to MongoDB.

```json
{
  "user_id":            "string",
  "tenant_id":          "string | null",
  "site_id":            "string | null",
  "onboarding_state":   "collecting | syncing | stable | drifted",
  "sample_count":       42,
  "last_drift":         0.31,
  "adaptive_threshold": 1.84,
  "feature_means":      [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
  "selected_features":  ["dwell_norm", "flight_norm", "jitter_norm"],
  "ema_profile":        [0.48, 0.52, 0.61, 0.39, 0.55, 0.47, 0.51, 0.49],
  "ema_variance":       [0.02, 0.03, 0.04, 0.02, 0.03, 0.02, 0.03, 0.02],
  "avg_theta":  0.87, "avg_h_exp": 0.79, "avg_dwell": 0.51,
  "avg_flight": 0.48, "avg_speed": 0.44, "avg_jitter": 0.38,
  "avg_accel":  0.41, "avg_rhythm": 0.55,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:05:00Z",
  "reset_at":   null
}
```

### `ProfileBuildStatus` response shape

Returned by `GET /biometric/profile/{user_id}/status` and embedded in every `POST /biometric/profile` response under the `profile_status` key:

```json
{
  "user_id":               "usr_abc123",
  "tenant_id":             "ten_xyz",
  "onboarding_state":      "stable",
  "sample_count":          57,
  "progress":              1.0,
  "drift_detection_armed": true,
  "last_drift":            0.31,
  "adaptive_threshold":    1.84,
  "selected_features":     ["dwell_norm", "flight_norm", "jitter_norm"],
  "updated_at":            "2024-01-01T00:05:00Z"
}
```

### `session/verify` response additions (v4.0.0)

```json
{
  "action":               "ok",
  "trust_score":          0.94,
  "e_rec":                0.04,
  "confidence":           "HIGH",
  "reason":               null,
  "session_invalidated":  false,
  "onboarding_state":     "stable",
  "drift_detection_armed": true
}
```

---

## User Flow

```
Register / Login
      │
      │  login response includes onboarding_state
      │
      ├─ collecting  ──▶  /profile-build  (progress bar; type to collect)
      │
      ├─ stable      ──▶  /dashboard  (drift detection armed)
      │
      └─ drifted     ──▶  /profile-build  (re-auth + reset prompt)
                                │
                                ├─ POST /biometric/profile/reset
                                │        └─▶ state = collecting
                                │
                                └─ POST /auth/logout → re-login
                                         └─▶ login auto-resets → collecting
```

`AuthContext` stores `onboardingState` and exposes `isProfileStable` so every route guard and component has a single, consistent flag with no local re-computation from raw sample counts.

---

## Production Deployment

### Build the production stack

```bash
docker-compose up -d --build
```

### Pre-train the RL governor (recommended)

```bash
python backend/train.py --episodes 200000 --out checkpoints/governor.pt
# ~20 min on CPU, ~3 min on GPU
```

### TLS certificates

```
nginx/ssl/fullchain.pem
nginx/ssl/privkey.pem
```

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `EP_SESSION_SECRET` | ✅ | Session secret used by the backend |
| `EP_SHADOW_SECRET` | — | Secondary secret for the watchdog / shadow paths |
| `MONGO_PASSWORD` | ✅ | MongoDB root password |
| `REDIS_PASSWORD` | ✅ | Redis password |
| `EP_RL_CHECKPOINT` | — | Path to pre-trained DQN weights |
| `EP_HONEYPOT_ENABLED` | — | `true`/`false` (default `true`) |
| `EP_CORS_ORIGINS` | — | Override allowed origins |

---

## Real-World Use Cases

| Industry | Problem | Entropy Prime Solution |
|---|---|---|
| Banking / Finance | Credential stuffing | Biometric signals + adaptive hashing |
| SaaS Platforms | Bot signups, fake accounts | Honeypot deception + session monitoring |
| Healthcare | Insider threats, session hijacking | Continuous trust scoring, passive re-auth |
| Cloud Services | Resource exhaustion, brute-force | RL-based resource governor |

---

## Tech Stack

- **Frontend:** React, Vite, TensorFlow.js, Recharts
- **Backend:** Python 3.13, FastAPI, PyTorch, Argon2-cffi, uvicorn + uvloop
- **ML:** 1D-CNN (biometrics), DQN (resource governor), Autoencoder (session trust)
- **Infra:** Docker Compose, Nginx, MongoDB 7, Redis 7

---

## Local Development

```bash
# Linux/macOS
./start.sh

# Windows
start.bat

# Manual backend
cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Manual frontend
npm install
npm run dev    # → http://localhost:3000

# Build SDK
scripts/bundle-sdk.sh
```

---

## Extending the System

- **Custom stable threshold:** Change `STABLE_SAMPLE_THRESHOLD` in `backend/database.py`. It is imported by `backend/models.py` and the sync endpoint from one location. Update the matching constant in `ProfileBuildPage.jsx`.
- **Real user database:** Replace the stub user-id generation in `/score` with a lookup against your user store.
- **Custom ML models:** Swap the 1D-CNN checkpoint via `EP_CNN_CHECKPOINT`, keeping input/output shapes compatible.
- **Webhooks / SIEM:** Add an `onBotDetected` webhook in `backend/honeypot.py`.
- **HTTPS in dev:** Use `mkcert` and point `VITE_API_URL` at `https://localhost:8000`.
- **Per-tenant alert tuning:** Use `POST /notifications/thresholds` — no code changes needed.
- **Admin monitoring:** Use `GET /admin/onboarding-summary?tenant_id=` to track how many users are stuck in `collecting` and tune your UX copy or sample threshold accordingly.

---

## Contributing

Pull requests and suggestions are welcome. Open an issue first for major changes so the design stays aligned.

- **Found a bug?** Open an issue with reproduction steps.
- **Want to contribute?** Fork the repo and open a PR against `main`.

---

## License

MIT — see [LICENSE](LICENSE).