# ⚡ ENTROPY PRIME — Zero-Trust Behavioral Biometrics Engine

> **Biological-physics security** — detect bots using neuromuscular jitter and temporal DNA, all without ever sending raw keystrokes to your server.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Build](https://img.shields.io/badge/build-passing-brightgreen)]()
[![SDK](https://img.shields.io/badge/SDK-entropy.min.js-blue)]()

---

## 5-Minute Onboarding

> New customer? Follow these four steps to go from zero to a running authentication system.

### Step 1 — Clone & configure (1 min)

```bash
git clone https://github.com/your-org/entropy-prime.git
cd entropy-prime

# Generate required secrets — do this once
export EP_SESSION_SECRET=$(openssl rand -hex 64)
export MONGO_PASSWORD=$(openssl rand -hex 24)
export REDIS_PASSWORD=$(openssl rand -hex 24)
export EP_DOMAIN=auth.yourdomain.com    # or localhost for local testing
```

> **Tip**: Persist these in a `.env` file (already in `.gitignore`) so you don't have to re-export them.

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

**Local development** (no TLS, hot-reload):
```bash
chmod +x start.sh && ./start.sh
# ✓ Backend  → http://localhost:8000
# ✓ Frontend → http://localhost:3000
# ✓ API docs → http://localhost:8000/docs
```

**Production** (Docker, with Nginx, Redis, MongoDB):
```bash
docker-compose -f docker-compose.prod.yml up -d
# ✓ All services start in ~30 seconds
```

Verify everything is healthy:
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
      console.log(`Humanity score: ${score.toFixed(2)} → ${label}`);
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

The SDK captures keystrokes and mouse movements **entirely in the browser** — raw signals never leave the device.

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

---

That's it — you now have bot detection running on your login page. Read on for architecture details, advanced configuration, and production hardening.

---

## Project Overview

Modern authentication is broken. Cookies are stolen. Browser fingerprints are spoofed. ENTROPY PRIME moves the trust anchor to **neuromuscular physics** — the unique, unclonable patterns in how a human being physically interacts with a keyboard and mouse.

### Core Algorithmic Phases

| Phase | Where | What happens |
|---|---|---|
| **Biological Gateway** | Browser | Captures dwell/flight times, velocity, jitter. A 1D-CNN outputs a humanity score θ ∈ [0,1]. |
| **Resource Governor** | Backend | A DQN agent selects Argon2id cost dynamically: expensive for bots, fast for verified humans. |
| **Offensive Deception** | Backend | Bots (θ < 0.1) receive synthetic session tokens and are silently routed to a honeypot. |
| **Session Watchdog** | Both | A deep autoencoder anchors a baseline; trust score decays if behaviour changes mid-session. |

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

Raw biometric signals are processed in-browser. The server cannot reconstruct keystroke timings or mouse paths from the three numbers it receives.

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
# Build SDK first (generates entropy.min.js + integrity hashes)
chmod +x scripts/bundle-sdk.sh
scripts/bundle-sdk.sh

# Build and start all production services
EP_DOMAIN=auth.example.com \
EP_SESSION_SECRET=$(cat .env | grep EP_SESSION_SECRET | cut -d= -f2) \
MONGO_PASSWORD=$(cat .env | grep MONGO_PASSWORD | cut -d= -f2) \
REDIS_PASSWORD=$(cat .env | grep REDIS_PASSWORD | cut -d= -f2) \
docker-compose -f docker-compose.prod.yml up -d --build
```

### Pre-train the RL governor (recommended)

```bash
python backend/train.py --episodes 200000 --out checkpoints/governor.pt
# Takes ~20 min on CPU, ~3 min on GPU. Significantly improves hashing cost decisions.
```

### TLS certificates

Place your certificates in `nginx/ssl/`:
```
nginx/ssl/fullchain.pem
nginx/ssl/privkey.pem
```

For automated Let's Encrypt certificates, mount a Certbot volume and add a renewal cron job.

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `EP_SESSION_SECRET` | ✅ | 64-byte hex secret for JWT signing |
| `EP_DOMAIN` | ✅ | Hostname (used for CORS and TLS) |
| `MONGO_PASSWORD` | ✅ | MongoDB password |
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
- **Backend:** Python 3.11, FastAPI, PyTorch, Argon2-cffi, uvicorn + uvloop
- **ML:** 1D-CNN (biometrics), DQN (resource governor), Autoencoder (session trust)
- **Infra:** Docker, Nginx, MongoDB 7, Redis 7

---

## Local Development

```bash
# Backend only
cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend only (separate terminal)
npm install
npm run dev    # → http://localhost:3000

# Build the SDK locally
scripts/bundle-sdk.sh
# Output in dist/entropy.min.js
```

---

## Extending the System

- **Real user database:** Replace `uid = "usr_" + secrets.token_hex(6)` in `/score` with a lookup against your user store. Add a `/login` endpoint that verifies the password hash before issuing the session token.
- **Custom ML models:** Swap the 1D-CNN checkpoint by setting `EP_CNN_CHECKPOINT` and ensuring the input/output shapes match the existing interface.
- **Webhooks:** Add a `onBotDetected` webhook in `backend/honeypot.py` to pipe threat-intelligence data to your SIEM.
- **HTTPS in dev:** Use `mkcert` to generate a local CA and point `VITE_API_URL` at `https://localhost:8000`.

---

## Contributing

Pull requests and suggestions are welcome. Please open an issue to discuss major changes before submitting a PR.

- **Found a bug?** Open an issue with reproduction steps.
- **Want to contribute?** Fork the repo and open a PR against `main`.

---

## License

MIT — see [LICENSE](LICENSE).