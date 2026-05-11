# Entropy Prime — Zero-Trust Authentication System

A **behavioral biometric + adaptive authentication** system that combines keystroke dynamics, pointer tracking, and machine learning to detect bots and enhance login security.

---

## Quick Summary

**What it does:**
- Users log in with email + password
- While typing, the system captures **keystroke timing, pointer speed, acceleration** (biometric signals)
- The backend runs these signals through **4 ML stages** to compute a human/bot score
- Based on the score, the system may:
  - Allow login normally
  - Ask for additional verification (challenge)
  - Block the request (bot detected)
- Argon2id password hashing makes cracking extremely expensive

**Where it runs:**
- **Frontend:** React SPA (browser) — captures biometric signals and collects user input
- **Proxy:** nginx — routes traffic, handles rate-limiting, serves static files
- **Backend:** FastAPI — runs authentication, pipeline orchestration, ML inference
- **Databases:** MongoDB (users, sessions), Redis (cache, rate-limits)
- **Models:** Pre-trained ML models (CNN1D, DQN, PPO, MAB) loaded from `checkpoints/`

---

## Argon2id Password Hashing

### What is Argon2id?
- **Modern, memory-hard password hashing algorithm**
- Resists both GPU attacks (memory-hard) and timing attacks (constant-time comparison)
- Recommended by OWASP for password storage

### Parameters Used

```
Argon2id( password, salt, params )
  memory_cost  (M):  64 MB to 512 MB   (amount of RAM required)
  time_cost    (t):  2 to 5 iterations  (number of passes)
  parallelism  (p):  4 to 8 threads     (degree of parallelism)
```

### Presets in Entropy Prime

| Preset | Memory | Iterations | Parallelism | Use Case |
|--------|--------|-----------|-------------|----------|
| ECONOMY | 64 MB | t=2 | p=4 | High-load servers, bot accounts |
| STANDARD | 128 MB | t=3 | p=4 | Default for normal users |
| HARD | 256 MB | t=4 | p=8 | Elevated-risk sessions |
| PUNISHER | 512 MB | t=5 | p=8 | Suspicious activity detected |

### How It Works

1. **Registration** (`POST /auth/register`):
   - User provides email + password
   - Backend hashes password with Argon2id (STANDARD preset by default)
   - Hash + salt stored in MongoDB
   - Actual password **never stored**

2. **Login** (`POST /auth/login`):
   - User submits email + password
   - Backend looks up user in MongoDB
   - Verifies password: `PasswordHasher().verify(stored_hash, plain_password)`
   - On match → creates session token + returns 200 OK
   - On mismatch → returns 401 Unauthorized

3. **Adaptive Hardening**:
   - During `/score` pipeline, if bot score is high → Stage 3 (Governor) selects HARD or PUNISHER
   - Next login attempt by that user will use the higher preset
   - Gradually increases cost for attackers

---

## 4-Stage ML Pipeline

### Architecture Overview

```
User Input (biometrics)
       ↓
   [Stage 1: Biometric]  → Feature extraction
       ↓
   [Stage 2: Honeypot]   → Bot trap classification
       ↓
   [Stage 3: Governor]   → Compute hardening + behavioral actions
       ↓
   [Stage 4: Watchdog]   → Drift detection + continuous monitoring
       ↓
   PipelineOutput (scores + recommendations)
```

### Stage 1: Biometric Interpretation
**Model:** CNN1D (1D Convolutional Neural Network)

- **Input:**
  - Keystroke timing (inter-key delays, hold times)
  - Pointer dynamics (speed, acceleration, pressure patterns)
  - Device/browser metadata
  
- **Processing:**
  - CNN1D extracts temporal patterns from keystroke sequences
  - Computes features: `theta` (human-ness score), `h_exp` (entropy)
  - Generates 32-dim latent vector (encoded behavior signature)

- **Output:** BiometricResult
  - `theta`: 0 (bot) to 1.0 (human) confidence score
  - `latent_vector`: 32-dim embedding (used by other stages)
  - `confidence`: HIGH / MEDIUM / LOW
  - `verdict`: HUMAN / SUSPECT / BOT

**File:** `backend/models/stage1_biometric.py`

---

### Stage 2: Honeypot Classification
**Model:** MAB (Multi-Armed Bandit) + Signature Matching

- **Purpose:** Detect bots using **decoy interactions** (invisible form fields, fake links)

- **How it works:**
  1. Backend sends "challenge config" with decoys (fake input fields)
  2. Human users ignore them; bots interact with them
  3. If user clicks/fills decoys → honeypot trigger detected → confirmed bot
  4. MAB algorithm learns which decoy types work best per attacker profile

- **3 Decoy Arms (strategies):**
  - **Arm 0 (Tarpit):** Heavy form decoys (fake email, password fields)
  - **Arm 1 (Echo):** Mirror decoys (slightly misspelled field names like "usernmae")
  - **Arm 2 (Canary):** Silent audit (invisible input + invisible anchor for crawlers)

- **Output:** HoneypotResult
  - `verdict`: HUMAN / BOT / SUSPICIOUS
  - `challenge_triggered`: True/False (did bot interact with decoys?)
  - `decoys_generated`: List of decoys sent (for SDK to inject)

**File:** `backend/models/stage2_honeypot.py`

---

### Stage 3: Governor (Resource Allocation)
**Models:** DQN (Deep Q-Network) + PPO (Proximal Policy Optimization)

Two sub-agents work sequentially:

#### 3a. DQN Agent → Argon2id Preset Selection
- **Input:** (theta, server_load, is_suspect)
- **Output:** Argon2id preset (ECONOMY → STANDARD → HARD → PUNISHER)
- **Logic:** 
  - Bot-like score + high server load → ECONOMY (fast, cheap)
  - Normal user → STANDARD
  - Elevated risk → HARD or PUNISHER
  
**Result:** Next login attempt uses the selected hashing preset

#### 3b. PPO Agent → Behavioral Response
- **Input:** (theta, server_load, risk_tolerance, verdict, latent_vector)
- **Output:** Action (ALLOW / LOG / CHALLENGE / BLOCK)
- **Actions:**
  - `ALLOW` – Let user proceed normally
  - `LOG` – Allow but create high-priority audit event
  - `CHALLENGE` – Require proof-of-work or CAPTCHA
  - `BLOCK` – Reject request outright

**Override Rules:**
- Bots on overloaded servers → ECONOMY preset (bypass DQN)
- Tenant hard-blocks enabled → BLOCK (bypass PPO)
- Trust score too low → FORCE_LOGOUT (security policy)

**File:** `backend/models/stage3_governor.py`

---

### Stage 4: Watchdog (Continuous Monitoring)
**Model:** PPO (Proximal Policy Optimization)

- **Purpose:** Detect **identity drift** during an active session (someone took over the account)

- **Input Vector (10-dim):**
  ```
  [lv_mean, lv_std, lv_max, lv_min,  ← latent vector statistics (4)
   lv_l2_norm,                         ← L2 norm (1)
   e_rec,                              ← reconstruction error (1)
   trust_score,                        ← running trust (1)
   e_rec_warn, e_rec_crit,
   trust_crit]                         ← threshold indicators (3)
  ```

- **Output:** WatchdogAction
  - `OK` – Session is stable
  - `PASSIVE_REAUTH` – Ask user to verify identity (silently re-check password)
  - `DISABLE_SENSITIVE_APIS` – Block high-privilege operations
  - `FORCE_LOGOUT` – Immediately end session (possible hijacking)

- **Fallback Rules** (when model unavailable):
  - If reconstruction error > CRITICAL → FORCE_LOGOUT
  - If reconstruction error > WARN → PASSIVE_REAUTH
  - Otherwise → OK

**File:** `backend/models/stage4_watchdog.py`

**Triggered by:** `/session/verify` endpoint (heartbeat checks during active session)

---

## API Endpoints (Simple Reference)

### Authentication
| Endpoint | Method | Purpose | Input |
|----------|--------|---------|-------|
| `/auth/register` | POST | Create new account | `{email, plain_password}` |
| `/auth/login` | POST | Authenticate user | `{email, plain_password}` |
| `/auth/logout` | POST | End session | `{session_token}` |

### Scoring & Verification
| Endpoint | Method | Purpose | Input |
|----------|--------|---------|-------|
| `/score` | POST | Run 4-stage pipeline | `{biometrics, latent_vector, user_agent, server_load}` |
| `/session/verify` | POST | Watchdog heartbeat | `{session_token, latent_vector}` |

### Password Management
| Endpoint | Method | Purpose | Input |
|----------|--------|---------|-------|
| `/password/hash` | POST | Hash a password | `{plain_password, memory, time, parallelism}` |
| `/password/verify` | POST | Verify password vs hash | `{plain_password, hash}` |

### Admin / Debug
| Endpoint | Method | Purpose | Notes |
|----------|--------|---------|-------|
| `/health` | GET | Health check | Docker healthcheck endpoint |
| `/admin/models-status` | GET | Model checkpoint info | Requires admin API key |
| `/admin/telemetry` | GET | Pipeline stats | Requires admin API key |

---

## Docker Stack (What Runs Where)

### Services
| Service | Container | Purpose | Config |
|---------|-----------|---------|--------|
| **nginx** | `entropy_nginx` | Reverse proxy, static serving, rate-limiting | `nginx/nginx.conf` |
| **backend** | `entropy_backend` | FastAPI server, ML pipeline, auth | `backend/main.py` |
| **mongodb** | `entropy_mongodb` | User storage, session persistence | `docker-compose.yml` |
| **redis** | `entropy_redis` | Rate-limit cache, token cache | Docker defaults |

### How to Start

```bash
# From repo root
docker compose up -d --build

# Check logs
docker logs entropy_backend --tail 200
docker logs entropy_nginx --tail 50
```

### Environment Variables
```
EP_SESSION_SECRET      # Secret key for session tokens
EP_API_KEY_SECRET      # Admin API key
MONGO_PASSWORD         # MongoDB root password
REDIS_PASSWORD         # Redis password
```

Store these in `all.env` (not committed to git).

---

## File Reference

### Backend
| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app, endpoint handlers |
| `backend/models/orchestrator.py` | Pipe line orchestration (glues all 4 stages) |
| `backend/models/stage1_biometric.py` | CNN1D biometric feature extraction |
| `backend/models/stage2_honeypot.py` | Honeypot decoy generation + bot detection |
| `backend/models/stage3_governor.py` | DQN + PPO for Argon2id + behavior |
| `backend/models/stage4_watchdog.py` | PPO for identity drift detection |
| `backend/models/contracts.py` | Data classes (shared types) |

### Frontend
| File | Purpose |
|------|---------|
| `src/pages/LoginPage.jsx` | Login/register UI + form handling |
| `src/services/api.js` | HTTP client wrapper (fetch + error handling) |
| `src/sdk/collectors.js` | Keystroke/pointer signal collection |
| `public/sdk/entropy.js` | SDK entry point (biometric capture) |

### Infrastructure
| File | Purpose |
|------|---------|
| `nginx/nginx.conf` | nginx config (proxy rules, rate-limits) |
| `docker-compose.yml` | Service definitions, env wiring |
| `Dockerfile` | Backend image build |

---

## Quick Demo (Manual Testing)

### 1. Register a User

```bash
curl -X POST http://localhost/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com", "plain_password":"TestPass123"}'
```

**Response:**
```json
{
  "email": "demo@example.com",
  "is_active": true
}
```

### 2. Login

```bash
curl -X POST http://localhost/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com", "plain_password":"TestPass123"}'
```

**Response:**
```json
{
  "session_token": "abc123xyz...",
  "user_id": "507f1f77bcf86cd799439011",
  "email": "demo@example.com"
}
```

### 3. Submit Biometric Score

```bash
curl -X POST http://localhost/score \
  -H "Content-Type: application/json" \
  -d '{
    "session_token": "abc123xyz...",
    "biometrics": {
      "keystroke_timings": [100, 150, 120, ...],
      "pointer_speeds": [50.5, 75.2, ...]
    },
    "latent_vector": [0.5, 0.2, ..., 0.9],
    "user_agent": "Mozilla/5.0...",
    "server_load": 0.35
  }'
```

**Response:**
```json
{
  "session_token": "abc123xyz...",
  "humanity_score": 0.92,
  "entropy_score": 0.78,
  "action_label": "ALLOW",
  "biometric": {"theta": 0.92, "verdict": "HUMAN"},
  "honeypot": {"verdict": "HUMAN", "challenged": false},
  "governor": {"preset": "STANDARD", "action": "ALLOW"},
  "watchdog": {"action": "OK", "drift_detected": false}
}
```

---

## Troubleshooting

### Problem: "Invalid image source" / Diagrams not rendering
→ Diagrams are now text-based. No image files needed.

### Problem: 405 Method Not Allowed
→ nginx is routing API requests to the SPA catch-all instead of backend.  
→ Fix: Verify `/auth/`, `/score`, `/session/` location blocks exist in `nginx/nginx.conf`.

### Problem: "Invalid credentials" on login
→ Check that user was registered with exact email + password.  
→ Verify MongoDB is running: `docker logs entropy_mongodb`.

### Problem: PPO/DQN errors in logs
→ Model checkpoint mismatch (wrong `.pt` file).  
→ Fallback logic will be used instead.  
→ Check `docker logs entropy_backend | grep -i "error"`.

---

## Presentation Notes

**Key Points to Highlight:**
1. **Behavioral Biometrics** – Don't rely on passwords alone; analyze how users type/move mouse
2. **Adaptive Authentication** – Response changes based on risk (easy for humans, hard for bots)
3. **Argon2id Hardening** – Memory-hard hashing makes brute-force attacks prohibitively expensive
4. **4-Stage Pipeline** – Each stage catches different attack patterns:
   - Stage 1: Raw keystroke/pointer analysis
   - Stage 2: Honeypot traps for bots
   - Stage 3: Dynamic policy (easy/hard hashing + challenges)
   - Stage 4: Drift detection (account hijacking)
5. **Docker Stack** – Modular, scalable, production-ready architecture

---

## Next Steps

- [ ] Deploy to cloud (AWS/GCP)
- [ ] Integrate with OIDC/OAuth providers
- [ ] Add SMS/email 2FA
- [ ] Build admin dashboard for monitoring
- [ ] Expand honeypot decoy library
- [ ] Fine-tune model parameters per use case
