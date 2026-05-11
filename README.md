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
# {"status":"ok","models":{"cnn":"loaded","dqn":"loaded","autoencoder":"loaded"}}
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
      // Attach token to your login form submission
      document.querySelector('#ep-token').value = token;
    }
  });
  ep.attach(document.querySelector('#login-form'));
</script>
```

**Option B — ES module import** (for React / Vue / bundled apps):

```bash
npm install entropy-prime   # or copy dist/entropy.esm.min.js locally
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
# The SDK posts to /score automatically. Verify a token manually:
curl -X POST http://localhost:8000/verify \
  -H "Content-Type: application/json" \
  -d '{"session_token": "<token-from-sdk>"}'

# Response:
# { "valid": true, "theta": 0.94, "label": "human", "expires_in": 3600 }
```

On your backend, reject requests where `theta < 0.5` or `valid: false`.
In the containerized stack, the public health URL is proxied through Nginx at `/health`.

---

That is the basic flow: collect signals in the browser, score them, issue a token, then verify that token on the server.

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
```

Raw biometric signals are processed in-browser. The server only sees compact derived features, not the full keystroke or mouse trace.

---

## SDK Reference

Use this section to map the browser API to the main runtime concepts: configuration, capture, scoring, and token handling.

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

This is the server-side surface area the SDK and your application depend on.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness check; returns model load status |
| `POST` | `/score` | Accepts θ, H_exp, latent vector; returns session token |
| `POST` | `/verify` | Validates a session token |
| `POST` | `/heartbeat` | Refreshes trust score during active session |
| `GET` | `/admin/models-status` | Reports CNN/DQN/autoencoder status |

Full interactive docs: `http://localhost:8000/docs`

---

## Production Deployment

### Build the production stack

```bash
# Build and start the main 4-service production stack
docker-compose up -d --build
```

The root `docker-compose.yml` starts Nginx, the FastAPI backend, MongoDB, and Redis on a shared bridge network. Nginx serves the SPA and reverse-proxies `/api/*`, `/auth/*`, `/admin/*`, `/score`, `/session/*`, `/password/*`, `/honeypot/*`, `/biometric/*`, `/telemetry`, and `/me` to the backend.

### Pre-train the RL governor (recommended)

```bash
python backend/train.py --episodes 200000 --out checkpoints/governor.pt
# Takes about 20 minutes on CPU and about 3 minutes on GPU. This improves hashing-cost decisions.
```

### TLS certificates

Place your certificates in `nginx/ssl/`:
```
nginx/ssl/fullchain.pem
nginx/ssl/privkey.pem
```

For automated Let's Encrypt certificates, mount a Certbot volume and add a renewal cron job.
If you are running the default compose stack exactly as checked in, Nginx is still the entry point for the app and API routes, but TLS configuration is only active once you wire in certificates.

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `EP_SESSION_SECRET` | ✅ | Session secret used by the backend |
| `EP_SHADOW_SECRET` | — | Secondary secret used by the watchdog / shadow paths |
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
# Linux/macOS: start backend and frontend together
./start.sh

# Windows: start MongoDB and Redis in Docker, then backend and frontend windows
start.bat

# Manual backend only
cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Manual frontend only (separate terminal)
npm install
npm run dev    # → http://localhost:3000

# Build the SDK locally
scripts/bundle-sdk.sh
# Output in dist/entropy.min.js
```

---

## Extending the System

- **Real user database:** Replace `uid = "usr_" + secrets.token_hex(6)` in `/score` with a lookup against your user store. Add a `/login` endpoint that verifies the password hash before issuing the session token.
- **Custom ML models:** Swap the 1D-CNN checkpoint by setting `EP_CNN_CHECKPOINT` and keeping the input and output shapes compatible with the current interface.
- **Webhooks:** Add an `onBotDetected` webhook in `backend/honeypot.py` to send threat-intelligence data to your SIEM.
- **HTTPS in dev:** Use `mkcert` to create a local CA and point `VITE_API_URL` at `https://localhost:8000`.

---

## Contributing

Pull requests and suggestions are welcome. Open an issue first for major changes so the design stays aligned.

- **Found a bug?** Open an issue with reproduction steps.
- **Want to contribute?** Fork the repo and open a PR against `main`.

---

## License

MIT — see [LICENSE](LICENSE).