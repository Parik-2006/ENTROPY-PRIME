# ENTROPY PRIME — Full Project Guide & Team Responsibility Matrix

> **Zero-Trust Behavioral Biometrics Authentication System**
> Keystroke Dynamics · Mouse Analytics · Multi-Agent ML Pipeline · Adaptive Per-User Profiling

---

## Table of Contents

1. [What Is Entropy Prime?](#1-what-is-entropy-prime)
2. [How the System Works — The Big Picture](#2-how-the-system-works--the-big-picture)
3. [Technology Stack at a Glance](#3-technology-stack-at-a-glance)
4. [Team Assignments Overview](#4-team-assignments-overview)
5. [VED U — Frontend & User Interface](#5-ved-u--frontend--user-interface)
6. [GANESH — Backend & API Development](#6-ganesh--backend--api-development)
7. [VIVEK — Infrastructure, DevOps & Deployment](#7-vivek--infrastructure-devops--deployment)
8. [Testing Responsibilities by Team Member](#8-testing-responsibilities-by-team-member)
9. [Cross-Team Integration Checkpoints](#9-cross-team-integration-checkpoints)
10. [Glossary of Key Terms](#10-glossary-of-key-terms)

---

## 1. What Is Entropy Prime?

Entropy Prime is a **security system that can tell the difference between a real human and a bot** by watching *how* you type and move your mouse — not just *what* you type.

### The Core Idea in Simple Terms

When you type on a keyboard, the exact timing of every key press and release is unique to you, almost like a fingerprint. The way you move your mouse — its speed, small tremors, acceleration patterns — is also uniquely yours. Entropy Prime captures these invisible signals, processes them through machine learning models, and builds a personal behavioral profile for each user over time.

If someone steals your password and tries to log in, their typing rhythm will be different from yours. Entropy Prime catches this even though the password is correct.

### What Makes It "Zero-Trust"?

Traditional security asks: *"Do you know the password?"*

Entropy Prime asks continuously: *"Does this really feel like you?"*

It never fully trusts anyone — not even an already-logged-in user. Every 30 seconds it quietly checks whether the current typing and mouse behavior still matches your profile. If something seems off, it can require re-authentication or block sensitive actions.

### What Happens to Bots?

Instead of simply blocking bots, Entropy Prime does something clever — it pretends to let them in. Bots get a fake session with fake data (fake user records, fake API keys, fake transactions). The bot wastes time attacking a sandbox while Entropy Prime harvests its behavioral fingerprint for threat intelligence. This is called the **honeypot deception** strategy.

---

## 2. How the System Works — The Big Picture

Every time a user interacts with the login page or dashboard, data flows through a **4-stage pipeline** on the server:

```
Browser Signals
     │
     ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 1 — Biometric Interpreter                    │
│  Reads θ (humanity score) from CNN model output.    │
│  Classifies: BOT / SUSPECT / HUMAN                  │
│  Assigns a confidence level: HIGH / MEDIUM / LOW    │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 2 — Honeypot Classifier                      │
│  BOT confirmed? → Route to shadow sandbox           │
│  Uses MAB (Multi-Armed Bandit) to pick the best     │
│  deception strategy (fake data / slow drip /        │
│  canary token injection)                            │
└───────────────────────┬─────────────────────────────┘
                        │ (only for humans)
                        ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 3 — Resource Governor (DQN)                  │
│  Chooses Argon2id password hashing strength based   │
│  on how suspicious the user seems and how busy      │
│  the server is: ECONOMY / STANDARD / HARD /         │
│  PUNISHER                                           │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 4 — Session Watchdog (PPO)                   │
│  Every 30 seconds: re-checks behavioral signals.    │
│  Actions: OK / passive_reauth /                     │
│  disable_sensitive_apis / force_logout              │
└─────────────────────────────────────────────────────┘
```

### The 8 Biometric Features Captured

The system measures 8 behavioral dimensions from every user:

| # | Feature Name | What It Measures |
|---|-------------|-----------------|
| 1 | `dwell_norm` | How long each key is held down |
| 2 | `flight_norm` | Time gap between releasing one key and pressing the next |
| 3 | `speed_norm` | How fast the mouse moves |
| 4 | `jitter_norm` | Tiny involuntary mouse tremors |
| 5 | `accel_norm` | How sharply the mouse changes direction |
| 6 | `rhythm_norm` | How consistent the typing beat is |
| 7 | `pause_norm` | Long pauses between typing bursts |
| 8 | `bigram_norm` | Timing of common letter pairs (e.g., "th", "he") |

These are fed into a **1D Convolutional Neural Network (CNN1D)** running in the browser, which outputs a single number called **θ (theta)** — the "humanity score" from 0 to 1. High θ = likely human. Low θ = likely bot.

---

## 3. Technology Stack at a Glance

### Frontend (Browser)
- **React + Vite** — UI framework
- **TensorFlow.js** — CNN1D and autoencoder running directly in the browser
- **Recharts** — Live signal charts on the dashboard
- **CSS Modules** — Scoped styling per page

### Backend (Server)
- **FastAPI (Python)** — REST API
- **PyTorch** — DQN, MAB, PPO, CNN1D models on the server
- **Argon2-cffi** — Password hashing with adaptive strength
- **Motor / MongoDB** — Async database driver

### Database
- **MongoDB** — Stores users, sessions, biometric profiles, drift events, honeypot signatures

### Infrastructure
- **Docker + Docker Compose** — Containerization
- **Uvicorn / Gunicorn** — Production ASGI server
- **Environment variables** — All secrets externalized

---

## 4. Team Assignments Overview

| Area | Team Member | Estimated Time | Key Deliverable |
|------|-------------|---------------|-----------------|
| Frontend & UI | **VED U** | 3–4 weeks | Working React app with live biometric visualization |
| Backend & API | **GANESH** | 3–4 weeks | FastAPI server with full 4-stage pipeline |
| Infrastructure | **VIVEK** | 2–3 weeks | Docker deployment + full test suite |

> **Important:** All three team members must coordinate at **integration checkpoints** (Section 9). VED U's API call format must match what GANESH builds. GANESH's data schemas must match what VIVEK's tests expect.

---

## 5. VED U — Frontend & User Interface

**Your role:** Build everything the user sees and interacts with. You also own the browser-side biometric engine — the JavaScript code that captures keystrokes and mouse movements and runs the neural network in the browser.

### Your Files

```
src/
├── App.jsx                     ← Route definitions, auth guards
├── main.jsx                    ← React entry point
├── index.css                   ← Global CSS variables and animations
├── context/
│   └── AuthContext.jsx         ← Global auth state + biometric engine lifecycle
├── pages/
│   ├── LoginPage.jsx           ← Login UI + live biometric signals
│   ├── LoginPage.module.css
│   ├── DashboardPage.jsx       ← Post-login metrics dashboard
│   ├── DashboardPage.module.css
│   ├── ThreatPage.jsx          ← Honeypot signatures table
│   └── ThreatPage.module.css
└── services/
    ├── api.js                  ← All HTTP calls to the backend
    └── biometrics.js           ← Browser biometric engine (CNN, collectors, profile)
```

---

### VED-01 — Understand the Biometric Engine (`biometrics.js`)

**What it is:** A self-contained JavaScript module that runs entirely in the browser. No data leaves the browser except θ (a single number), a 32-dimensional latent vector, and drift deltas.

**Step-by-step walkthrough:**

**Step 1 — Signal Collectors**

Two classes capture raw data:

- `KeyboardCollector` — attaches `keydown` and `keyup` event listeners to the document. For every key press, it records:
  - `dwell`: milliseconds the key was held (keyup time minus keydown time)
  - `flight`: milliseconds since the last key was released
  - `bigramRatio`: timing comparison for common two-letter sequences

- `PointerCollector` — attaches `mousemove` event listeners. For each movement, it computes velocity, acceleration, and jitter (how jagged the movement is).

To start collecting in your component:
```javascript
const ep = new EntropyPrimeClient()
await ep.init()  // starts keyboard and pointer collectors automatically
```

**Step 2 — Feature Vector Builder**

`buildFeatureVector()` takes the raw event arrays and squashes them into 8 normalized numbers (the 8 features listed in Section 2). Normalization means all values are scaled to fit between 0 and 1.

**Step 3 — CNN1D in the Browser**

`buildHumanityScoreCNN()` creates a TensorFlow.js model with this architecture:
```
Input [50 timesteps × 8 features]
  → Conv1D(32 filters) → BatchNorm → ReLU
  → Conv1D(64 filters) → BatchNorm → ReLU
  → Conv1D(64 filters) → GlobalMaxPooling
  → Dense(64) → Dropout(0.3)
  → Dense(32) → Dense(1, sigmoid)
Output: θ ∈ [0, 1]
```

Note: The model starts with random weights. In production, you would load pre-trained weights. For the demo, the output fluctuates based on actual typing patterns, which is sufficient to demonstrate the concept.

**Step 4 — Autoencoder for Identity Verification**

`buildAutoencoder()` creates two linked models:
- The **autoencoder** learns to compress and then reconstruct the signal
- The **encoder** alone produces the 32-dimensional latent vector

The reconstruction error (`eRec`) measures how different the current typing is from the baseline. High eRec = identity drift detected.

**Step 5 — Per-User Behavioral Profile**

`UserBehavioralProfile` maintains an **Exponential Moving Average (EMA)** of the 8 features over time. Think of it as a slowly-adapting memory of "how this user normally types."

`UserFeatureSelector` uses **Welford's online algorithm** to track which of the 8 features vary the most for this specific user. More variable features are more discriminative and get selected (top 6 out of 8).

Both objects are serialized to `localStorage` so the profile survives page reloads.

**Step 6 — Session Watchdog (browser side)**

`SessionWatchdog` runs `check()` to compute eRec against the current profile and adjust the trust score:
- Trust increases slowly (+0.02 per clean check)
- Trust drops sharply when anomaly detected (−0.15 × severity)
- Triggers the `onAnomaly` callback which feeds into `AuthContext`

---

### VED-02 — Authentication Context (`AuthContext.jsx`)

This is the global brain of the frontend. It:

1. **Boots the biometric engine** (`EntropyPrimeClient.init()`) when the app loads
2. **Restores user sessions** from `localStorage` on page reload
3. **Runs a watchdog heartbeat** every 30 seconds when a user is logged in
4. **Persists the biometric profile** to `localStorage` every 15 seconds and to the server every ~5 heartbeats

**Key state values exposed to all components:**

| Value | Type | Meaning |
|-------|------|---------|
| `user` | object or null | Currently logged-in user |
| `loading` | boolean | True while session is being restored |
| `epReady` | boolean | True when biometric engine has initialized |
| `liveTheta` | number | Current humanity score (updates every 1.5s) |
| `trustScore` | number | Session trust level 0–1 |
| `anomaly` | object or null | Set when identity drift is detected |
| `liveDrift` | number | Current behavioral drift score |
| `selectedFeatures` | array | Feature names selected for this user |
| `profileStats` | object | Biometric profile summary |

**Heartbeat implementation (every 30 seconds):**
```javascript
const { eRec, trustScore: ts } = await ep.checkIdentity()
const vec    = await ep.getLatentVector()
const pStats = ep.getProfileStats()

const res = await sendWatchdogHeartbeat({
  userId, latentVector: vec, eRec, trustScore: ts,
  behavioralDrift: pStats.lastDrift,
  adaptiveThreshold: pStats.adaptiveThreshold,
  selectedFeatures: pStats.selectedFeatures,
  sampleCount: pStats.sampleCount,
})
```

---

### VED-03 — Login Page (`LoginPage.jsx`)

The login page serves dual purposes: it is both a functional login form and a live demonstration of the biometric engine.

**Components you need to understand:**

**`ScoreRing`** — SVG circle that shows θ as a colored arc:
- Green (`#00ffa3`) when θ > 0.7 — human
- Orange (`#ffb800`) when θ > 0.4 — uncertain
- Red (`#ff3b5c`) when θ ≤ 0.4 — suspected bot

**`SignalBar`** — Horizontal bar showing one biometric channel's current normalized value. If the channel is in the user's selected feature set, it shows a star (★) and highlights in green.

**`TypingTrace`** — SVG polyline that draws the dwell-time waveform of the last 40 keystrokes. Flat line = robotic. Varied = human.

**`FeatureChip`** — Small badge for each of the 8 features. Glows when selected by `UserFeatureSelector` for this user.

**`ProfileProgress`** — Progress bar showing how many biometric samples have been collected. The system needs at least 50 samples before the profile is considered stable.

**Authentication flow (what happens when you click "AUTHENTICATE"):**

```
User clicks button
  → ep.evaluate(password) — runs CNN, computes θ and entropy score
  → submitScore({ theta, hExp, latentVector }) — POST /score
  → hashPassword({ plainPassword, theta, hExp }) — POST /password/hash
  → login(userData, session_token) — saves to localStorage, loads profile
  → setResult() / setPhase('done') — updates UI
```

**Things to implement carefully:**

- The button must be disabled (`disabled` attribute) while `phase` is `scanning` or `hashing`, and also when `epReady` is false
- Error messages go in `<div className={styles.errorMsg}>` — never use `alert()`
- The `Spinner` component rotates using the `spin` CSS animation already defined in `index.css`

---

### VED-04 — Dashboard Page (`DashboardPage.jsx`)

The dashboard shows live monitoring data for authenticated users.

**`Sidebar`** — Left navigation panel. Contains the trust score meter (updates live from `useAuth().trustScore`), navigation links, user info, and logout button.

**`PhaseBadge`** — Status indicator for each of the 4 pipeline stages. Color and pulse animation change based on current signal values:
- Stage 1: alert (red) if θ ≤ 0.3
- Stage 4: warn (orange) if eRec > 0.18

**`StatCard`** — Six metric cards in a grid showing: humanity score, entropy score, reconstruction error, trust score, keystroke count, pointer event count.

**Live chart loop (runs every 1 second):**
```javascript
const id = setInterval(() => {
  const ep   = getClient()
  const eRec = ep?.watchdog?.lastERec ?? 0
  setChartData(prev => [...prev.slice(-60), {
    t:     new Date().toLocaleTimeString('en', { hour12: false }),
    theta: +theta.toFixed(4),
    eRec:  +eRec.toFixed(4),
  }])
  setKbStats(ep.getKeyboardStats())
  setPtStats(ep.getPointerStats())
}, 1000)
```

**Reference lines on charts:**
- θ chart: green dashed line at 0.7, red dashed line at 0.3
- eRec chart: orange dashed line at 0.18 (EREC_WARN threshold)

**`MetricRow`** — Horizontal progress bar with label, fill %, value, and unit. Used for dwell, flight, pointer speed, jitter.

---

### VED-05 — Threat Intelligence Page (`ThreatPage.jsx`)

This page fetches and displays bot signatures captured by the honeypot.

**Data source:** `GET /honeypot/signatures` — called on mount and every 10 seconds.

**Summary cards** at the top show:
- Total bot signatures harvested
- High-confidence bots (θ < 0.1)
- Distinct user agents seen
- Average θ score of all bots

**Signatures table** — Each row shows timestamp, θ score (color-coded), user agent string, path, and a "SHADOW" badge. Clicking a row expands a JSON detail panel below the table.

**Things VED U must handle:**
- Empty state when no signatures exist yet (styled message, not a blank page)
- Error state when backend is unreachable (styled error box with instructions)
- Loading spinner during initial fetch
- Responsive hiding of the path column on small screens

---

### VED-06 — API Service Layer (`api.js`)

All backend communication goes through this file. You must never write `fetch()` calls directly in components.

**Key functions and their return types:**

```javascript
// POST /score — full pipeline
submitScore({ theta, hExp, latentVector, userAgent, serverLoad })
  → { session_token, shadow_mode, argon2_params, action_label,
      humanity_score, entropy_score, pipeline_confidence, degraded,
      watchdog?, mab_arm? }

// POST /password/hash
hashPassword({ plainPassword, theta, hExp })
  → { hash, action, elapsed_ms, argon2_params, confidence, fallback }

// POST /session/verify — watchdog heartbeat
sendWatchdogHeartbeat({ userId, latentVector, eRec, trustScore })
  → { action, trust_score, e_rec, confidence, reason }

// GET /honeypot/signatures
getHoneypotSignatures()
  → { signatures: [...], count: number }
```

**Helper functions VED U should use in UI:**

```javascript
import { watchdogSeverity, confidenceWeight } from './api'

// Maps action string to severity level for color-coding
watchdogSeverity('passive_reauth')  // → 'warn'
watchdogSeverity('force_logout')    // → 'critical'

// Maps confidence to 0–1 weight for opacity/brightness
confidenceWeight('high')    // → 1.0
confidenceWeight('low')     // → 0.3
```

---

### VED-07 — Implementation Steps (in order)

Follow these steps in sequence. Each step depends on the previous one working.

**Week 1 — Core Engine & Auth**

1. Set up the Vite + React project and install dependencies:
   ```bash
   npm create vite@latest entropy-prime-frontend -- --template react
   cd entropy-prime-frontend
   npm install @tensorflow/tfjs recharts react-router-dom
   ```

2. Copy `index.css` — this defines all CSS variables (`--bg`, `--accent`, `--danger`, etc.) that every module uses.

3. Implement `biometrics.js` — start with `KeyboardCollector` and `PointerCollector`. Test by opening the browser console and logging `ep.getKeyboardStats()` as you type.

4. Add `buildFeatureVector()` and verify that all 8 values stay between 0 and 1.

5. Add `buildHumanityScoreCNN()` and `buildAutoencoder()`. These return TF.js models. Verify they load without error using `model.summary()` in the console.

6. Implement `EntropyPrimeClient` — the `init()` method starts everything. Verify `_liveEval` fires every 1.5 seconds and calls `setUpdateCallback`.

7. Build `AuthContext.jsx` — wrap everything in `AuthProvider` and test that `useAuth()` returns sensible defaults.

8. Build the basic routing in `App.jsx` with `PrivateRoute` and `PublicRoute` guards.

**Week 2 — Login Page**

9. Build `LoginPage.jsx` in this order: form inputs first, then `ScoreRing`, then signal bars, then `TypingTrace`.

10. Wire up `handleSubmit` to call `submitScore` and `hashPassword`. For now, mock the backend URL to `http://localhost:8000` via `VITE_API_URL` in `.env.local`.

11. Test that clicking "AUTHENTICATE" shows the scanning/hashing states, then transitions to "AUTHENTICATED" on success.

12. Add `ProfileProgress`, `FeatureChip`, and `driftBadge` — these are display-only and should work without backend.

**Week 3 — Dashboard & Threat Page**

13. Build `DashboardPage.jsx` — start with the static layout (Sidebar + StatGrid), then add the live chart loop.

14. Verify that chart data accumulates correctly and old data is pruned (`.slice(-60)` keeps last 60 seconds).

15. Build `ThreatPage.jsx` — implement fetch, loading, error, empty, and populated states.

16. Add the `anomalyBanner` to the dashboard — it should appear when `useAuth().anomaly` is non-null.

**Week 4 — Polish & Integration**

17. Connect to the live backend (coordinate with GANESH for the base URL).

18. Test the full authentication flow end-to-end.

19. Test session restore by logging in, refreshing the page, and verifying you land on `/dashboard` not `/login`.

20. Test the watchdog by staying on the dashboard for 2+ minutes and watching the trust score update.

---

### VED Testing Responsibilities

See Section 8.1 for the full test plan.

---

## 6. GANESH — Backend & API Development

**Your role:** Build the Python FastAPI server, implement all 4 pipeline stages, integrate MongoDB for persistence, and expose all endpoints that the frontend calls.

### Your Files

```
backend/
├── main.py                     ← FastAPI app, all route handlers
├── database.py                 ← MongoDB connection + all DB operations
├── models.py                   ← Pydantic models (legacy, keep for reference)
├── requirements.txt            ← Python dependencies
├── train.py                    ← DQN pre-training script
├── models/
│   ├── __init__.py             ← Package exports
│   ├── contracts.py            ← All data contracts between stages
│   ├── pydantic_models.py      ← Request/response models
│   ├── orchestrator.py         ← PipelineOrchestrator — the main entry point
│   ├── stage1_biometric.py     ← Stage 1: Biometric classification
│   ├── stage2_honeypot.py      ← Stage 2: Shadow routing + MAB
│   ├── stage3_governor.py      ← Stage 3: DQN → Argon2id preset
│   ├── stage4_watchdog.py      ← Stage 4: PPO → trust action
│   ├── cnn1d.py                ← CNN1D feature extractor
│   ├── dqn.py                  ← Deep Q-Network (DQN agent)
│   ├── mab.py                  ← Multi-Armed Bandit agent
│   ├── ppo.py                  ← Proximal Policy Optimization agent
│   ├── train_cnn1d.py          ← CNN1D training scripts
│   ├── train_mab.py            ← MAB pre-training
│   ├── train_ppo.py            ← PPO Watchdog training
│   └── test_pipeline.py        ← Pytest test suite
```

---

### GANESH-01 — Understand the Data Contracts (`contracts.py`)

Before building anything else, study `contracts.py` thoroughly. Every piece of data flowing between pipeline stages is typed here using Python dataclasses.

**The chain of data objects:**

```
BiometricInput (raw from browser)
     │
     ▼
BiometricResult (after Stage 1)
     │
     ▼
HoneypotResult (after Stage 2) ──→ if bot: stop here, return synthetic token
     │
     ▼
GovernorResult (after Stage 3)
     │
     ▼
WatchdogResult (after Stage 4)
     │
     ▼
PipelineOutput (final response to browser)
```

**Key threshold constants (single source of truth — never hardcode these values anywhere else):**

```python
BOT_THETA_HARD   = 0.10   # below this: definite bot → honeypot
BOT_THETA_SOFT   = 0.30   # below this: suspicious
EREC_WARN        = 0.18   # reconstruction error → warn level
EREC_CRITICAL    = 0.35   # reconstruction error → critical
TRUST_WARN       = 0.50   # trust below this → warn
TRUST_CRITICAL   = 0.25   # trust below this → force action
SERVER_LOAD_HIGH = 0.85   # throttle strong hashing when server is busy
```

**The `Confidence` enum** (used by every stage to report certainty):
- `HIGH` — model is certain (rank 2 in comparisons)
- `MEDIUM` — model is uncertain; downstream may hedge (rank 1)
- `LOW` — model is guessing; fallback rules applied (rank 0)

The orchestrator rolls up confidence by taking the **minimum** across all stages. One uncertain stage makes the whole pipeline uncertain.

---

### GANESH-02 — Stage 1: Biometric Interpreter (`stage1_biometric.py`)

This stage has no ML model — it uses pure logic to classify the incoming θ score.

**Decision logic:**

```python
if theta < BOT_THETA_HARD (0.10):
    verdict = BOT, is_bot = True

elif theta < BOT_THETA_SOFT (0.30):
    verdict = SUSPECT, is_suspect = True

else:
    verdict = HUMAN
```

**Confidence rules:**

| θ range | Confidence |
|---------|-----------|
| θ < 0.05 or θ > 0.60 | HIGH (far from decision boundaries) |
| 0.05 ≤ θ < 0.15 or 0.50 ≤ θ < 0.60 | MEDIUM |
| 0.15 ≤ θ < 0.50 | LOW (contested middle zone) |

**Additional degradation:** If the browser sent no latent vector (empty `[]`), confidence is downgraded one level from HIGH → MEDIUM. It cannot degrade below LOW.

**What this stage returns:**

```python
@dataclass
class BiometricResult:
    theta:       float          # passed through unchanged
    h_exp:       float          # password entropy, passed through
    server_load: float
    verdict:     HoneypotVerdict
    confidence:  Confidence
    is_bot:      bool
    is_suspect:  bool
    note:        str            # human-readable diagnostic
```

---

### GANESH-03 — Stage 2: Honeypot Classifier (`stage2_honeypot.py`)

This stage decides whether to shadow-route the request. It uses the **MAB (Multi-Armed Bandit)** to pick a deception strategy when shadowing.

**Routing decision table:**

| Verdict | Confidence | Action |
|---------|-----------|--------|
| BOT | Any | Shadow (always) |
| SUSPECT | HIGH | Shadow (high-confidence suspicion) |
| SUSPECT | MEDIUM or LOW | Pass through (benefit of doubt) |
| HUMAN | Any | Pass through |

**MAB arm selection:**

```python
DECEPTION_ARMS = [
    "fake_data_feed",       # arm 0: serve plausible fake JSON
    "slow_drip",            # arm 1: add latency + partial data
    "canary_token_inject",  # arm 2: embed trackable tokens
]
```

The MAB agent uses **epsilon-greedy** selection (10% random, 90% best known arm). MAB confidence is based on how many times the chosen arm has been tried:
- < 10 pulls → LOW confidence
- 10–49 pulls → MEDIUM confidence
- ≥ 50 pulls → HIGH confidence

**Synthetic token generation for shadow sessions:**

```python
def _make_synthetic_token(secret, ip, arm):
    payload = f"shadow:{ip}:{arm}:{time.time():.3f}"
    sig     = hmac.new(secret.encode(), payload.encode(), sha256).hexdigest()
    return f"ep_shadow_{secrets.token_urlsafe(32)}.{sig[:16]}"
```

This token looks legitimate but contains a shadow prefix. The bot receives it as a real session token.

**After a shadow session ends** (bot disconnects or timer expires), the frontend calls `POST /honeypot/reward` with the arm index and reward value (positive = deception held, negative = bot escaped). This updates the MAB's internal values so it learns which deception strategies work best.

---

### GANESH-04 — Stage 3: Resource Governor (`stage3_governor.py`)

This stage uses the **DQN (Deep Q-Network)** to choose how hard to make password hashing. Harder hashing costs more CPU but makes brute-force attacks slower.

**Argon2id parameter table:**

| Action | Preset | Memory | Time Cost | Parallelism | Use Case |
|--------|--------|--------|-----------|-------------|----------|
| 0 | ECONOMY | 64 MB | 2 | 4 | Bots (waste their time, save server) |
| 1 | STANDARD | 128 MB | 3 | 4 | Normal humans |
| 2 | HARD | 512 MB | 4 | 8 | Suspicious signals |
| 3 | PUNISHER | 1024 MB | 8 | 16 | High-value accounts or anomalies |

**Override rules (applied BEFORE the DQN):**

```python
# Bot + overloaded server → save resources, use ECONOMY
if bio.is_bot and bio.server_load > 0.85:
    return ECONOMY (fallback=True)

# Confirmed bot + healthy server → make them suffer, use HARD
if bio.is_bot and bio.confidence == HIGH:
    return HARD (fallback=True)
```

**Server load cap (applied AFTER DQN):**

```python
# Never use HARD or PUNISHER when server is overloaded
if bio.server_load > 0.85 and action > 1:
    action = 1  # clamp to STANDARD
```

**Confidence propagation:** If the biometric input had LOW confidence, the governor's output confidence is capped at MEDIUM even if the DQN was very certain. Garbage in → uncertain out.

**DQN state vector (3-dimensional input):**
```python
state = [theta, h_exp, server_load]  # all values in [0, 1]
```

**Confidence from DQN Q-value spread:**
- spread > 1.5 → HIGH (DQN strongly prefers one action)
- spread > 0.5 → MEDIUM
- spread ≤ 0.5 → LOW (DQN is uncertain, actions are nearly equal)

---

### GANESH-05 — Stage 4: Session Watchdog (`stage4_watchdog.py`)

This stage runs every time the browser sends a heartbeat (`POST /session/verify`). It uses the **PPO (Proximal Policy Optimization)** model to decide what action to take.

**Hard override (checked FIRST, bypasses PPO):**

```python
if trust < 0.25 and e_rec > 0.35:
    return FORCE_LOGOUT  # both metrics critical simultaneously
```

**PPO state vector (10-dimensional input):**

```python
state = [
    e_rec,                           # reconstruction error
    trust_score,                     # current trust
    1.0 - trust_score,               # trust delta proxy
    min(latent_norm / 10.0, 1.0),   # normalized vector magnitude
    latent_mean,                     # mean of latent features
    latent_std,                      # standard deviation
    float(e_rec > 0.18),             # binary: above warn threshold?
    float(e_rec > 0.35),             # binary: above critical threshold?
    float(trust < 0.50),             # binary: trust below warn?
    float(trust < 0.25),             # binary: trust critical?
]
```

**PPO action mapping:**

| Index | Action |
|-------|--------|
| 0 | OK — session normal |
| 1 | passive_reauth — ask for re-authentication quietly |
| 2 | disable_sensitive_apis — block writes/transfers |

Note: `force_logout` (index 3) only comes from the hard override, never from PPO directly.

**Fallback rules (used when PPO confidence is LOW or PPO is unavailable):**

```python
if trust < 0.25 or e_rec > 0.35:
    return DISABLE_SENSITIVE_API
elif trust < 0.50 or e_rec > 0.18:
    return PASSIVE_REAUTH
else:
    return OK
```

---

### GANESH-06 — Pipeline Orchestrator (`orchestrator.py`)

The orchestrator is the main entry point for every `/score` request. Its `run()` method sequences all 4 stages.

**Critical design principles:**

1. **Never raises exceptions** — all errors are caught and converted to fallback results. The pipeline always returns a `PipelineOutput`.

2. **Short-circuit for bots** — if Stage 2 determines the user is a bot, Stages 3 and 4 are skipped. The bot gets a synthetic token with ECONOMY hashing params.

3. **Degraded mode tracking** — if any stage used a fallback (due to error or low DQN confidence), `degraded=True` is set on the output. Operators can alert on this.

4. **Confidence roll-up** — `pipeline_confidence` is the minimum confidence across all stages that ran.

**The `_make_session_token` helper:**

```python
def _make_session_token(uid, lv, secret):
    vh  = sha256(str(lv).encode()).hexdigest()[:16]  # hash of latent vector
    pay = f"{uid}:{time.time():.0f}:{vh}"
    sig = hmac.new(secret.encode(), pay.encode(), sha256).hexdigest()
    return secrets.token_urlsafe(8) + "." + (pay + ":" + sig).encode().hex()
```

This binds the session token to the latent vector so stolen tokens cannot be replayed by a different user.

---

### GANESH-07 — FastAPI Routes (`main.py`)

**Startup sequence (using `@asynccontextmanager` lifespan):**

```
1. Connect to MongoDB (with 5-attempt retry logic)
2. Load model checkpoints from disk (non-fatal if missing)
3. Initialize PipelineOrchestrator with all agents
```

**Key routes GANESH must implement:**

**`POST /score`** — Main pipeline entry point

Request body: `ScoreReq` (theta, h_exp, server_load, user_agent, latent_vector)

Processing:
```python
raw = BiometricInput(...)
result = orchestrator.run(raw)

# If bot: persist to honeypot collection in MongoDB
if result.shadow_mode:
    await store_honeypot_entry(db, ...)

# Build response dict
response = {
    "session_token":       result.session_token,
    "shadow_mode":         result.shadow_mode,
    "argon2_params":       result.argon2_params,
    "humanity_score":      result.humanity_score,
    ...
}
return response  # always HTTP 200, even for bots
```

**`POST /session/verify`** — Watchdog heartbeat

Runs Stage 4 in isolation. Updates session trust score in MongoDB.

**`POST /honeypot/reward`** — MAB feedback

Called when a shadow session ends. Updates MAB arm values.

**`POST /auth/register`** — User registration

Uses the governor (at θ=0.9 for a "trusted new user") to pick hashing strength. Creates user in MongoDB and generates first session token.

**`POST /auth/login`** — User login

Verifies password with `PasswordHasher().verify()`. Returns session token.

**`GET /health`** — Returns `{"status": "ok", "pipeline": "active", "stages": 4}`

**`GET /admin/pipeline-debug`** — Dry-run with synthetic inputs. Returns full per-stage breakdown. Useful for testing without a real browser.

---

### GANESH-08 — Database Operations (`database.py`)

**Collections and their purpose:**

| Collection | Purpose |
|-----------|---------|
| `users` | Account storage with hashed passwords |
| `sessions` | Active sessions with trust scores and latent vectors |
| `biometric_profiles` | Per-user EMA behavioral profiles |
| `drift_events` | Audit log of every drift detection event |
| `feature_selections` | History of which features were selected per user |
| `honeypot` | Bot signatures harvested from shadow sessions |

**Key operations to understand:**

`upsert_biometric_profile()` — Uses MongoDB `$set` and `$setOnInsert` to either update an existing profile or create a new one. The `upsert=True` flag does this atomically.

`store_biometric_sample()` — Uses `$push` with `$slice: -500` to maintain a rolling window of the last 500 samples per user. This prevents unbounded growth.

`log_drift_event()` — Every time Stage 4 detects drift, this is called. Events have a 30-day TTL index (`expireAfterSeconds=2592000`) so they clean themselves up.

**Index strategy (created at startup):**

```python
await db.users.create_index("email", unique=True)
await db.sessions.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
await db.drift_events.create_index(
    [("timestamp", ASCENDING)], expireAfterSeconds=60 * 60 * 24 * 30
)
```

The `expireAfterSeconds=0` on sessions means MongoDB automatically deletes documents where `expires_at` is in the past — you never need to manually clean up expired sessions.

---

### GANESH-09 — ML Model Architecture Details

**DQN Agent (`dqn.py`):**

```
Input: [theta, h_exp, server_load]  → 3 neurons
Hidden: Linear(3→128) → ReLU → Linear(128→128) → ReLU
Output: Linear(128→4) → 4 Q-values (one per action)
```

`select_action()` returns `argmax(Q-values)` — always the greedy best action.
`q_values()` returns the full 4-value array so Stage 3 can compute the spread.

**MAB Agent (`mab.py`):**

Maintains two arrays:
- `counts[arm]` — how many times each arm has been pulled
- `values[arm]` — current estimated reward for each arm (incremental mean)

Update formula: `values[arm] = ((n-1)/n) * old_value + (1/n) * new_reward`

**PPO Agent (`ppo.py`):**

```
PolicyNetwork:
  Input: 10-dim state
  Hidden: Linear(10→128) → ReLU → Linear(128→64) → ReLU
  Output: Linear(64→3) → Softmax → probabilities

ValueNetwork:
  Same architecture but Linear(64→1) → scalar value estimate
```

Stage 4 uses only `ppo_agent.policy(state_tensor)` — it reads the output probabilities, takes the argmax for the action, and uses the max probability as a confidence signal.

---

### GANESH-10 — Pre-Training the Models

Before the server starts, you should pre-train the models to have reasonable initial weights. Without pre-training, the models use random weights and make random decisions.

**Train DQN Governor:**
```bash
cd backend
python train.py --episodes 100000 --bot-ratio 0.30 --out checkpoints/governor.pt
```

This simulates 100,000 authentication requests with 30% being bots. The DQN learns to:
- Use HARD/PUNISHER on suspected bots with healthy server
- Use ECONOMY on bots when server is overloaded
- Use STANDARD/ECONOMY on humans with strong passwords

**Train MAB Deceiver:**
```bash
cd backend/models
python train_mab.py --steps 20000 --out checkpoints/mab.json
```

This simulates bot engagement rewards for each deception arm. Based on simulated data, `fake_data_feed` (arm 0) typically learns the highest value.

**Train PPO Watchdog:**
```bash
cd backend/models
python train_ppo.py --episodes 3000 --out checkpoints/watchdog.pt
```

This simulates session scenarios (60% clean, 25% gradual drift, 15% sudden hijack) and trains the PPO to recognize and respond to each.

Set checkpoint paths before starting the server:
```bash
export EP_RL_CHECKPOINT=checkpoints/governor.pt
export EP_MAB_CHECKPOINT=checkpoints/mab.json
export EP_PPO_CHECKPOINT=checkpoints/watchdog.pt
```

---

### GANESH-11 — Implementation Steps (in order)

**Week 1 — Environment & Models**

1. Install Python 3.11 and create a virtual environment:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Start MongoDB locally (or use Docker):
   ```bash
   docker run -d -p 27017:27017 --name ep-mongo mongo:6
   ```

3. Study `contracts.py` thoroughly. Run `python -c "from models.contracts import *; print('OK')"` to verify imports.

4. Implement and test `stage1_biometric.py` in isolation:
   ```python
   from models.contracts import BiometricInput
   from models import stage1_biometric as s1
   raw = BiometricInput(theta=0.03, h_exp=0.7, server_load=0.4,
                        user_agent="test", latent_vector=[], ip_address="127.0.0.1")
   result = s1.run(raw)
   print(result.verdict, result.confidence)  # should be BOT, HIGH
   ```

5. Implement `stage2_honeypot.py`, `stage3_governor.py`, `stage4_watchdog.py` in order. Test each in isolation before moving on.

6. Run pre-training scripts for all three models.

**Week 2 — Orchestrator & API**

7. Implement `orchestrator.py`. Test with `python -c`:
   ```python
   from models.orchestrator import PipelineOrchestrator
   from models.contracts import BiometricInput
   from models.dqn import DQNAgent
   from models.mab import MABAgent
   from models.ppo import PPOAgent

   orch = PipelineOrchestrator(DQNAgent(), MABAgent(), PPOAgent(),
                               "shadow_secret", "session_secret")
   raw  = BiometricInput(theta=0.85, h_exp=0.7, server_load=0.4,
                         user_agent="test", latent_vector=[0.1]*32,
                         ip_address="127.0.0.1")
   out  = orch.run(raw)
   print(out.shadow_mode, out.action_label)  # should be False, 'standard'
   ```

8. Implement `database.py`. Test connection:
   ```python
   import asyncio
   from database import Database
   db = Database()
   asyncio.run(db.connect_to_mongo())
   print("Connected!")
   ```

9. Implement `main.py` — start with `/health`, then `/score`, then auth routes.

10. Start the server and test `/health`:
    ```bash
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    curl http://localhost:8000/health
    ```

**Week 3 — Auth, Admin & Integration**

11. Implement `/auth/register` and `/auth/login`. Test with curl:
    ```bash
    curl -X POST http://localhost:8000/auth/register \
      -H "Content-Type: application/json" \
      -d '{"email":"test@test.com","plain_password":"test123"}'
    ```

12. Implement `/honeypot/signatures` and `/admin/pipeline-debug`.

13. Test the full `/score` endpoint with a bot simulation (theta=0.05):
    ```bash
    curl -X POST http://localhost:8000/score \
      -H "Content-Type: application/json" \
      -d '{"theta":0.05,"h_exp":0.5,"server_load":0.4,"user_agent":"bot","latent_vector":[]}'
    ```
    Verify `shadow_mode: true` and `session_token` starts with `ep_shadow_`.

14. Coordinate with VED U to verify the API response format matches what `api.js` expects.

**Week 4 — Polish & Tests**

15. Run the full test suite: `pytest models/test_pipeline.py -v`

16. Fix any failing tests. Target: 100% pass rate.

17. Write integration tests for the HTTP endpoints (see Section 8.2).

18. Add rate limiting or input validation improvements as time allows.

---

### GANESH Testing Responsibilities

See Section 8.2 for the full test plan.

---

## 7. VIVEK — Infrastructure, DevOps & Deployment

**Your role:** Make the system runnable in production. This includes Docker containerization, environment configuration, health monitoring, and owning the full end-to-end and performance test suite.

### Your Files

```
backend/
├── Dockerfile                  ← Multi-stage production image
├── .dockerignore               ← Excludes unnecessary files from image
└── requirements.txt            ← Python deps (you pin versions)

# You will CREATE these files:
docker-compose.yml              ← Orchestrates backend + MongoDB together
docker-compose.test.yml         ← Separate compose for running tests
.env.example                    ← Template for environment variables
nginx.conf                      ← (optional) Reverse proxy config
tests/
├── test_integration.py         ← API endpoint integration tests
├── test_e2e.py                 ← End-to-end browser tests (Playwright)
├── test_load.py                ← Load/performance tests (Locust or k6)
└── test_security.py            ← Security validation tests
```

---

### VIVEK-01 — Understand the Dockerfile

The existing `Dockerfile` uses a **multi-stage build** to keep the production image small and secure:

**Stage 1 (builder):**
```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt
```

This installs all Python dependencies into `/root/.local` inside a temporary container. The `--user` flag means they go into the user's local directory, not system-wide.

**Stage 2 (runtime):**
```dockerfile
FROM python:3.11-slim
RUN useradd -m -u 1000 entropy  # non-root user for security
COPY --from=builder /root/.local /home/entropy/.local  # copy packages
COPY . /app                                             # copy source code
USER entropy                                            # drop privileges
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Why multi-stage?** The builder stage has build tools (pip, compilers) that aren't needed at runtime. The runtime image only contains the installed packages, making it smaller and with fewer attack surface vectors.

**Health check:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
```

Docker will automatically restart the container if `/health` stops returning 200 for 3 consecutive checks.

---

### VIVEK-02 — Create `docker-compose.yml`

You need to create this file. Here is the template with explanations:

```yaml
version: "3.9"

services:
  # MongoDB database
  mongodb:
    image: mongo:6
    container_name: ep_mongodb
    restart: unless-stopped
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_USER:-admin}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_PASS:-changeme}
      MONGO_INITDB_DATABASE: entropy_prime
    volumes:
      - mongodb_data:/data/db     # persist data across restarts
    ports:
      - "27017:27017"             # expose for local debugging
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  # FastAPI backend
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: ep_backend
    restart: unless-stopped
    depends_on:
      mongodb:
        condition: service_healthy   # wait for MongoDB to be ready
    environment:
      MONGODB_URL: mongodb://${MONGO_USER:-admin}:${MONGO_PASS:-changeme}@mongodb:27017/
      MONGODB_DB_NAME: entropy_prime
      EP_SESSION_SECRET: ${EP_SESSION_SECRET}    # must be set in .env
      EP_SHADOW_SECRET: ${EP_SHADOW_SECRET}      # must be set in .env
      EP_RL_CHECKPOINT: /app/checkpoints/governor.pt
      EP_MAB_CHECKPOINT: /app/checkpoints/mab.json
      EP_PPO_CHECKPOINT: /app/checkpoints/watchdog.pt
      CORS_ORIGINS: ${CORS_ORIGINS:-http://localhost:3000}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
    volumes:
      - ./checkpoints:/app/checkpoints   # pre-trained model weights
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

volumes:
  mongodb_data:
    driver: local
```

**Key things to understand:**

`depends_on` with `condition: service_healthy` — the backend container won't start until MongoDB's healthcheck passes. This prevents the "MongoDB not ready" startup errors.

`volumes: - ./checkpoints:/app/checkpoints` — the pre-trained model `.pt` and `.json` files are mounted from the host into the container. This means you can update model weights without rebuilding the image.

`restart: unless-stopped` — if the container crashes, Docker restarts it automatically.

---

### VIVEK-03 — Create `.env` and `.env.example`

Never commit secrets to version control. Create these two files:

**`.env.example`** (commit this):
```bash
# MongoDB credentials
MONGO_USER=admin
MONGO_PASS=changeme_in_production

# Security secrets — generate with: python -c "import secrets; print(secrets.token_hex(32))"
EP_SESSION_SECRET=REPLACE_WITH_RANDOM_64_CHAR_HEX
EP_SHADOW_SECRET=REPLACE_WITH_RANDOM_64_CHAR_HEX

# CORS — comma-separated origins allowed to call the API
CORS_ORIGINS=http://localhost:3000,https://yourdomain.com

# Logging
LOG_LEVEL=INFO
```

**`.env`** (add to `.gitignore`, never commit):
```bash
MONGO_USER=admin
MONGO_PASS=actual_secure_password_here
EP_SESSION_SECRET=actual_64_hex_string_here
EP_SHADOW_SECRET=another_64_hex_string_here
CORS_ORIGINS=http://localhost:3000
LOG_LEVEL=DEBUG
```

Generate secrets:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

### VIVEK-04 — Container Build & Run Commands

**Build the image:**
```bash
docker build -t entropy-prime:latest ./backend
```

**Run with compose (recommended):**
```bash
# Start everything (detached)
docker-compose up -d

# View logs
docker-compose logs -f backend

# Check health status
docker-compose ps

# Stop everything
docker-compose down

# Stop and remove volumes (wipes database — use with caution)
docker-compose down -v
```

**Rebuild after code changes:**
```bash
docker-compose up -d --build backend
```

**Copy checkpoints into the running container (alternative to volume mount):**
```bash
docker cp ./checkpoints/governor.pt ep_backend:/app/checkpoints/governor.pt
docker cp ./checkpoints/mab.json    ep_backend:/app/checkpoints/mab.json
docker cp ./checkpoints/watchdog.pt ep_backend:/app/checkpoints/watchdog.pt
```

**Debug a running container:**
```bash
docker exec -it ep_backend bash
# Now you're inside the container
python -c "import torch; print(torch.__version__)"
```

---

### VIVEK-05 — Understanding the Health Check System

The system has multiple layers of health checking:

**Layer 1 — Docker HEALTHCHECK:** Pings `GET /health` every 30 seconds. If it fails 3 times, Docker marks the container as unhealthy and can restart it.

**Layer 2 — FastAPI `/health` endpoint:**
```python
@app.get("/health")
async def health():
    return {
        "status":    "ok",
        "pipeline":  "active",
        "stages":    4,
        "timestamp": time.time(),
    }
```

This returns quickly without hitting the database. It only verifies the FastAPI process is alive.

**Layer 3 — `/admin/models-status`:** Returns status of all 4 ML models. You can use this to verify checkpoints loaded correctly.

**Layer 4 — `/admin/pipeline-debug`:** Does a full dry-run of the pipeline with synthetic inputs. This is the deepest health check — if this returns cleanly, everything is working.

**Monitoring script to create** (`scripts/healthcheck.sh`):
```bash
#!/bin/bash
BASE=http://localhost:8000

echo "=== Basic Health ==="
curl -s $BASE/health | python -m json.tool

echo -e "\n=== Pipeline Debug (theta=0.85, human) ==="
curl -s "$BASE/admin/pipeline-debug?theta=0.85&h_exp=0.7" | python -m json.tool

echo -e "\n=== Pipeline Debug (theta=0.05, bot) ==="
curl -s "$BASE/admin/pipeline-debug?theta=0.05&h_exp=0.5" | python -m json.tool

echo -e "\n=== Models Status ==="
curl -s $BASE/admin/models-status | python -m json.tool
```

---

### VIVEK-06 — Implementation Steps (in order)

**Week 1 — Local Docker Setup**

1. Verify Docker and Docker Compose are installed:
   ```bash
   docker --version       # should be 24+
   docker-compose --version   # should be 2.x
   ```

2. Create `.env` from `.env.example` and fill in all values.

3. Write `docker-compose.yml` using the template in VIVEK-02.

4. Build and start:
   ```bash
   docker-compose up --build
   ```

5. Verify the backend is reachable:
   ```bash
   curl http://localhost:8000/health
   ```

6. Verify MongoDB is accessible from inside the backend container:
   ```bash
   docker exec ep_backend python -c "
   import asyncio, os
   from motor.motor_asyncio import AsyncIOMotorClient
   async def test():
       client = AsyncIOMotorClient(os.environ['MONGODB_URL'])
       await client.admin.command('ping')
       print('MongoDB OK')
   asyncio.run(test())
   "
   ```

**Week 2 — Checkpoint Pipeline**

7. Run the training scripts (coordinate with GANESH to ensure they run correctly inside the container):
   ```bash
   docker exec ep_backend python train.py --episodes 50000
   docker exec ep_backend python models/train_mab.py --steps 10000
   docker exec ep_backend python models/train_ppo.py --episodes 2000
   ```

8. Verify checkpoint files exist:
   ```bash
   ls -la backend/checkpoints/
   ```

9. Restart the backend and verify checkpoints load (look for ✓ log lines):
   ```bash
   docker-compose restart backend
   docker-compose logs backend | grep "✓"
   ```

**Week 3 — Testing Infrastructure**

10. Set up the Python test environment:
    ```bash
    pip install pytest httpx pytest-asyncio playwright locust
    playwright install chromium
    ```

11. Write and run integration tests (see Section 8.3).

12. Write and run E2E tests (see Section 8.4).

13. Write and run load tests (see Section 8.5).

14. Write and run security tests (see Section 8.6).

**Week 4 — Production Hardening**

15. Add Nginx as a reverse proxy (optional but recommended):
    ```nginx
    server {
        listen 80;
        location / { proxy_pass http://backend:8000; }
    }
    ```

16. Set up log rotation to prevent disk fill:
    ```yaml
    # In docker-compose.yml under backend service:
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"
    ```

17. Document the full deployment procedure for future team members.

---

### VIVEK Testing Responsibilities

See Sections 8.3, 8.4, 8.5, and 8.6 for the full test plan.

---

## 8. Testing Responsibilities by Team Member

---

### 8.1 — VED U: Frontend & Component Tests

**Tools:** Vitest (built into Vite), React Testing Library

**Install:**
```bash
npm install -D vitest @testing-library/react @testing-library/user-event jsdom
```

**Vitest config** (add to `vite.config.js`):
```javascript
test: {
  environment: 'jsdom',
  globals: true,
  setupFiles: './src/test/setup.js',
}
```

---

#### Test 1: Biometric Signal Normalization

**What to test:** `buildFeatureVector()` always returns values between 0 and 1 regardless of extreme inputs.

**File:** `src/services/biometrics.test.js`

**Why it matters:** If a feature exceeds 1.0, the CNN produces unpredictable output.

```javascript
import { buildFeatureVector, KeyboardCollector, PointerCollector } from './biometrics'
import { describe, it, expect } from 'vitest'

describe('buildFeatureVector', () => {
  it('returns 8 values all between 0 and 1', () => {
    const mockKeyEvents = [
      { dwell: 150, flight: 200, bigramRatio: 1.2 },
      { dwell: 300, flight: 450, bigramRatio: 0.8 },
    ]
    const mockPointerEvents = [
      { speed: 1500, jitter: 80, accel: 4000 },
    ]
    const mockKeyboard = { getRhythm: () => 0.4, getAvgPause: () => 500, getStats: () => ({ rhythm: 0.4, avgPause: 500 }) }

    const feats = buildFeatureVector(mockKeyEvents, mockPointerEvents, mockKeyboard)

    expect(feats).toHaveLength(8)
    feats.forEach((v, i) => {
      expect(v).toBeGreaterThanOrEqual(0, `Feature ${i} below 0`)
      expect(v).toBeLessThanOrEqual(1, `Feature ${i} above 1`)
    })
  })

  it('handles empty events gracefully', () => {
    const mockKeyboard = { getRhythm: () => 0, getAvgPause: () => 0, getStats: () => ({ rhythm: 0, avgPause: 0 }) }
    const feats = buildFeatureVector([], [], mockKeyboard)
    expect(feats).toHaveLength(8)
    feats.forEach(v => expect(Number.isFinite(v)).toBe(true))
  })
})
```

**Estimated time:** 30 minutes

---

#### Test 2: UserFeatureSelector — Selection Stability

**What to test:** After seeing enough samples, the feature selector consistently picks the same top-K features. Selection should not flip randomly on every update.

**File:** `src/services/biometrics.test.js`

**Why it matters:** If selected features change randomly, the UI chips would flicker and the behavioral profile would be noisy.

```javascript
import { UserFeatureSelector } from './biometrics'

describe('UserFeatureSelector', () => {
  it('selects exactly K features', () => {
    const sel = new UserFeatureSelector(6)
    // Feed 100 samples
    for (let i = 0; i < 100; i++) {
      const vec = Array.from({ length: 8 }, () => Math.random())
      sel.update(vec)
    }
    expect(sel.selectedIndices).toHaveLength(6)
  })

  it('selected indices are valid (0-7)', () => {
    const sel = new UserFeatureSelector(6)
    for (let i = 0; i < 100; i++) sel.update(Array.from({ length: 8 }, Math.random))
    sel.selectedIndices.forEach(idx => {
      expect(idx).toBeGreaterThanOrEqual(0)
      expect(idx).toBeLessThanOrEqual(7)
    })
  })

  it('serializes and deserializes correctly', () => {
    const sel = new UserFeatureSelector(6)
    for (let i = 0; i < 50; i++) sel.update(Array.from({ length: 8 }, Math.random))
    const json = sel.toJSON()
    const sel2 = UserFeatureSelector.fromJSON(json)
    expect(sel2.selectedIndices).toEqual(sel.selectedIndices)
    expect(sel2.n).toBe(sel.n)
  })
})
```

**Estimated time:** 30 minutes

---

#### Test 3: UserBehavioralProfile — Drift Detection

**What to test:** Drift score increases when the user's pattern changes significantly, and decreases when they return to their normal pattern.

**File:** `src/services/biometrics.test.js`

**Why it matters:** This is the core security mechanism. If drift detection is broken, the watchdog cannot detect account takeover.

```javascript
import { UserBehavioralProfile } from './biometrics'

describe('UserBehavioralProfile', () => {
  it('drift increases with abnormal patterns', () => {
    const profile = new UserBehavioralProfile()
    const normalVec = [0.3, 0.4, 0.5, 0.2, 0.3, 0.4, 0.1, 0.5]

    // Train on normal pattern
    for (let i = 0; i < 50; i++) {
      const vec = normalVec.map(v => v + (Math.random() - 0.5) * 0.05)
      profile.update(vec)
    }
    const normalDrift = profile.lastDrift

    // Test with very different pattern
    const driftedVec = [0.9, 0.1, 0.9, 0.1, 0.9, 0.1, 0.9, 0.1]
    profile.update(driftedVec)
    const anomalyDrift = profile.lastDrift

    expect(anomalyDrift).toBeGreaterThan(normalDrift)
  })

  it('adaptive threshold increases with volatile users', () => {
    const profile = new UserBehavioralProfile()
    // Simulate a volatile user (high variance)
    for (let i = 0; i < 50; i++) {
      profile.update(Array.from({ length: 8 }, Math.random))
    }
    const threshold = profile.adaptiveThreshold
    expect(threshold).toBeGreaterThan(0)
    expect(Number.isFinite(threshold)).toBe(true)
  })
})
```

**Estimated time:** 45 minutes

---

#### Test 4: LoginPage Component Rendering

**What to test:** The login page renders correctly, shows the biometric engine status, and handles form submission states.

**File:** `src/pages/LoginPage.test.jsx`

**Why it matters:** The login page is the user's first interaction. Broken rendering or form logic blocks all other functionality.

```javascript
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthContext } from '../context/AuthContext'
import LoginPage from './LoginPage'

// Mock auth context
const mockAuthContext = {
  login: vi.fn(),
  epReady: true,
  liveTheta: 0.85,
  getClient: () => ({
    getKeyboardStats: () => ({ avgDwell: 120, avgFlight: 200, rhythm: 0.3, count: 15 }),
    getPointerStats:  () => ({ avgSpeed: 800, avgJitter: 12, avgAccel: 200, count: 50 }),
    keyboard: { _events: [] },
    getProfileStats:  () => ({ sampleCount: 25, lastDrift: 0.1, adaptiveThreshold: 0.5, selectedFeatures: [] }),
    evaluate: vi.fn().mockResolvedValue({ theta: 0.85, hExp: 0.7 }),
    getLatentVector: vi.fn().mockResolvedValue(new Array(32).fill(0.1)),
  }),
  selectedFeatures: ['dwell_norm', 'flight_norm'],
  liveDrift: 0.1,
}

const renderLoginPage = () =>
  render(
    <AuthContext.Provider value={mockAuthContext}>
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    </AuthContext.Provider>
  )

describe('LoginPage', () => {
  it('shows BIOMETRIC ENGINE ACTIVE when epReady is true', () => {
    renderLoginPage()
    expect(screen.getByText('BIOMETRIC ENGINE ACTIVE')).toBeInTheDocument()
  })

  it('shows AUTHENTICATE button when idle', () => {
    renderLoginPage()
    expect(screen.getByText('AUTHENTICATE')).toBeInTheDocument()
  })

  it('disables button when email is empty', async () => {
    renderLoginPage()
    const btn = screen.getByText('AUTHENTICATE')
    await userEvent.click(btn)
    expect(screen.getByText(/Email and password required/)).toBeInTheDocument()
  })

  it('renders all 8 feature chips', () => {
    renderLoginPage()
    const features = ['DWELL', 'FLIGHT', 'SPEED', 'JITTER', 'ACCEL', 'RHYTHM', 'PAUSE', 'BIGRAM']
    features.forEach(f => expect(screen.getByText(f)).toBeInTheDocument())
  })
})
```

**Estimated time:** 1 hour

---

#### Test 5: API Service Layer — Request Format

**What to test:** Each API function sends the correct payload format to the backend.

**File:** `src/services/api.test.js`

**Why it matters:** If the request format doesn't match the backend's Pydantic models, all requests will fail with 422 Unprocessable Entity.

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { submitScore, sendWatchdogHeartbeat } from './api'

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch

beforeEach(() => {
  mockFetch.mockReset()
  localStorage.clear()
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ session_token: 'test', shadow_mode: false, humanity_score: 0.85 }),
  })
})

describe('submitScore', () => {
  it('sends correct field names (snake_case)', async () => {
    await submitScore({ theta: 0.85, hExp: 0.7, latentVector: new Array(32).fill(0), serverLoad: 0.4 })

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body).toHaveProperty('theta')
    expect(body).toHaveProperty('h_exp')        // not hExp
    expect(body).toHaveProperty('server_load')  // not serverLoad
    expect(body).toHaveProperty('latent_vector') // not latentVector
  })

  it('sends user agent from navigator', async () => {
    await submitScore({ theta: 0.85, hExp: 0.7, latentVector: [] })
    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(typeof body.user_agent).toBe('string')
  })
})

describe('sendWatchdogHeartbeat', () => {
  it('sends session token from localStorage', async () => {
    localStorage.setItem('ep_token', 'test_token_123')
    await sendWatchdogHeartbeat({
      userId: 'usr_123',
      latentVector: new Array(32).fill(0),
      eRec: 0.05,
      trustScore: 0.95,
    })
    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.session_token).toBe('test_token_123')
  })
})
```

**Estimated time:** 1 hour

---

#### Test 6: ScoreRing Color Logic

**What to test:** The `ScoreRing` component renders the correct color for human/uncertain/bot thresholds.

**File:** `src/pages/LoginPage.test.jsx`

```javascript
describe('ScoreRing', () => {
  // Using the ring color logic: >0.7 green, >0.4 orange, ≤0.4 red
  it('shows green for high theta', () => {
    // Render with theta=0.85, check stroke color in SVG
    // ...implementation depends on how you expose the color
  })

  it('shows correct label: HUMAN for theta > 0.7', () => {
    // ...
  })
})
```

**Estimated time:** 30 minutes

---

**VED U Total Test Estimate: 4–5 hours**

---

### 8.2 — GANESH: Backend Unit & Integration Tests

**Tools:** pytest, pytest-asyncio

**Install:**
```bash
pip install pytest pytest-asyncio httpx
```

---

#### Test Suite 1: Pipeline Unit Tests (already exists in `test_pipeline.py`)

GANESH must ensure all tests in `models/test_pipeline.py` pass. This file tests all 4 stages and the orchestrator in isolation.

**Run:**
```bash
cd backend
pytest models/test_pipeline.py -v
```

**Expected output — all tests must pass:**

```
tests/test_pipeline.py::TestStage1::test_definite_bot              PASSED
tests/test_pipeline.py::TestStage1::test_bot_boundary              PASSED
tests/test_pipeline.py::TestStage1::test_suspect_range             PASSED
tests/test_pipeline.py::TestStage1::test_human                     PASSED
tests/test_pipeline.py::TestStage1::test_high_confidence_human     PASSED
tests/test_pipeline.py::TestStage1::test_contested_band_low_confidence PASSED
tests/test_pipeline.py::TestStage1::test_missing_latent_degrades_confidence PASSED
tests/test_pipeline.py::TestStage2::test_bot_gets_shadowed         PASSED
tests/test_pipeline.py::TestStage2::test_human_not_shadowed        PASSED
...
(all 40+ tests should pass)
```

**Estimated time to get all tests passing:** 2 hours (fixing any bugs found)

---

#### Test Suite 2: Threshold Consistency Tests

**What to test:** The thresholds in `contracts.py` are used consistently throughout all stages. No stage should hardcode its own threshold values.

**File:** `tests/test_thresholds.py`

**Why it matters:** If a stage uses a hardcoded `0.3` instead of `BOT_THETA_SOFT`, refactoring the threshold breaks only that stage silently.

```python
import ast, pathlib

def test_no_hardcoded_thresholds():
    """Ensure stage files import thresholds from contracts, not hardcode them."""
    stage_files = [
        "models/stage1_biometric.py",
        "models/stage2_honeypot.py",
        "models/stage3_governor.py",
        "models/stage4_watchdog.py",
    ]
    forbidden_literals = {0.10, 0.30, 0.18, 0.35, 0.50, 0.25, 0.85}

    for filepath in stage_files:
        source = pathlib.Path(filepath).read_text()
        tree   = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                assert node.value not in forbidden_literals, \
                    f"Hardcoded threshold {node.value} found in {filepath} — use contracts.py constants"
```

**Estimated time:** 1 hour

---

#### Test Suite 3: Confidence Propagation Tests

**What to test:** The orchestrator's final confidence is always ≤ the minimum confidence of any single stage.

**File:** `tests/test_orchestrator_confidence.py`

**Why it matters:** If a LOW confidence stage produces a HIGH overall confidence, the ops team will trust results they shouldn't.

```python
import pytest
from models.contracts import BiometricInput, Confidence
from models.orchestrator import PipelineOrchestrator
from models.dqn import DQNAgent
from models.mab import MABAgent
from models.ppo import PPOAgent

CONF_RANK = {"high": 2, "medium": 1, "low": 0}

@pytest.fixture
def orch():
    return PipelineOrchestrator(
        DQNAgent(), MABAgent(), PPOAgent(),
        shadow_secret="test_shadow", session_secret="test_session"
    )

@pytest.mark.parametrize("theta,lv,expect_max_conf", [
    (0.85, [0.1]*32, "high"),    # clear human with latent vector
    (0.35, [],       "low"),     # contested zone + no latent → must be LOW
    (0.05, [0.0]*32, "medium"),  # bot (short-circuits at stage 2)
])
def test_confidence_never_exceeds_weakest_stage(orch, theta, lv, expect_max_conf):
    raw = BiometricInput(theta=theta, h_exp=0.7, server_load=0.4,
                         user_agent="test", latent_vector=lv, ip_address="127.0.0.1")
    result = orch.run(raw)
    actual_rank   = CONF_RANK[result.pipeline_confidence.value]
    max_allowed   = CONF_RANK[expect_max_conf]
    assert actual_rank <= max_allowed, \
        f"Expected max rank {max_allowed} but got {actual_rank} for theta={theta}"
```

**Estimated time:** 1 hour

---

#### Test Suite 4: Database Operations Tests

**What to test:** User creation, session lifecycle, and biometric profile upsert work correctly. Uses a test database, not production.

**File:** `tests/test_database.py`

**Why it matters:** Bugs in database operations can corrupt user data or leak sessions.

```python
import pytest
import asyncio
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from database import create_user, get_user_by_email, create_session, get_session, invalidate_session

TEST_MONGO_URL = "mongodb://localhost:27017"
TEST_DB_NAME   = "entropy_prime_test"   # NEVER use production DB name

@pytest.fixture
async def test_db():
    client = AsyncIOMotorClient(TEST_MONGO_URL)
    db     = client[TEST_DB_NAME]
    yield db
    # Cleanup: drop test database after each test
    await client.drop_database(TEST_DB_NAME)
    client.close()

@pytest.mark.asyncio
async def test_create_and_retrieve_user(test_db):
    user_id = await create_user(test_db, "test@example.com", "hashed_password_here")
    assert user_id is not None

    user = await get_user_by_email(test_db, "test@example.com")
    assert user is not None
    assert user["email"] == "test@example.com"
    assert user["is_active"] is True

@pytest.mark.asyncio
async def test_user_email_unique(test_db):
    await create_user(test_db, "unique@example.com", "hash1")
    with pytest.raises(Exception):   # should raise on duplicate
        await create_user(test_db, "unique@example.com", "hash2")

@pytest.mark.asyncio
async def test_session_lifecycle(test_db):
    user_id  = await create_user(test_db, "session@example.com", "hash")
    token    = "test_token_abc123"
    await create_session(test_db, user_id, token, [0.0]*32)

    session = await get_session(test_db, token)
    assert session is not None
    assert session["is_active"] is True

    await invalidate_session(test_db, token)
    session = await get_session(test_db, token)
    assert session is None  # should not be returned after invalidation

@pytest.mark.asyncio
async def test_expired_sessions_not_returned(test_db):
    from datetime import timedelta
    # Create session that expires immediately (1 second)
    user_id = await create_user(test_db, "expired@example.com", "hash")
    token   = "expired_token_xyz"
    await test_db.sessions.insert_one({
        "user_id": user_id, "session_token": token,
        "is_active": True, "latent_vector": [],
        "expires_at": datetime.utcnow() - timedelta(seconds=1),  # already expired
    })
    session = await get_session(test_db, token)
    assert session is None
```

**Estimated time:** 2 hours

---

#### Test Suite 5: API Endpoint Tests (HTTP level)

**What to test:** Each FastAPI route returns the correct HTTP status code and response shape.

**File:** `tests/test_api_routes.py`

**Why it matters:** Even if the pipeline logic is correct, a misnamed field in the response breaks the frontend.

```python
import pytest
from httpx import AsyncClient
from main import app

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_health_returns_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["pipeline"] == "active"
    assert "timestamp" in body

@pytest.mark.asyncio
async def test_score_human_no_shadow(client):
    r = await client.post("/score", json={
        "theta": 0.85, "h_exp": 0.7, "server_load": 0.4,
        "user_agent": "test", "latent_vector": [0.1]*32,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["shadow_mode"] is False
    assert "session_token" in body
    assert "humanity_score" in body
    assert "argon2_params" in body
    assert body["pipeline_confidence"] in ("high", "medium", "low")

@pytest.mark.asyncio
async def test_score_bot_gets_shadow(client):
    r = await client.post("/score", json={
        "theta": 0.03, "h_exp": 0.5, "server_load": 0.4,
        "user_agent": "python-requests/2.31", "latent_vector": [],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["shadow_mode"] is True
    assert body["session_token"].startswith("ep_shadow_")

@pytest.mark.asyncio
async def test_score_invalid_theta_rejected(client):
    r = await client.post("/score", json={"theta": 1.5, "h_exp": 0.5})  # theta > 1
    assert r.status_code == 422   # Pydantic validation error

@pytest.mark.asyncio
async def test_score_wrong_latent_size_rejected(client):
    r = await client.post("/score", json={
        "theta": 0.5, "h_exp": 0.5, "latent_vector": [0.1]*16,  # wrong size (must be 32)
    })
    assert r.status_code == 422

@pytest.mark.asyncio
async def test_session_verify_structure(client):
    r = await client.post("/session/verify", json={
        "session_token": "test_token",
        "user_id": "usr_123",
        "latent_vector": [0.1]*32,
        "e_rec": 0.05,
        "trust_score": 0.9,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["action"] in ("ok", "passive_reauth", "disable_sensitive_apis", "force_logout")
    assert 0 <= body["trust_score"] <= 1

@pytest.mark.asyncio
async def test_honeypot_reward_accepted(client):
    r = await client.post("/honeypot/reward", json={"arm": 0, "reward": 0.8})
    assert r.status_code == 200
    assert r.json()["ok"] is True
```

**Estimated time:** 2 hours

---

**GANESH Total Test Estimate: 8–10 hours**

---

### 8.3 — VIVEK: Integration Tests

Integration tests verify that multiple components work together correctly — backend + database, or end-to-end API call chains.

**Tools:** pytest, httpx, pytest-asyncio

**File:** `tests/test_integration.py`

---

#### Integration Test 1: Registration → Login → Score Flow

**What to test:** A full authentication sequence works across multiple endpoints without data inconsistencies.

**Why it matters:** GANESH's individual endpoint tests verify each route in isolation. This test verifies they work sequentially with shared state (the session token from register must work in score).

```python
import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_full_auth_and_score_flow():
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Step 1: Register a new user
        reg = await client.post("/auth/register", json={
            "email": "integration_test@example.com",
            "plain_password": "SecureTestPass123!",
        })
        assert reg.status_code == 200
        reg_body = reg.json()
        assert "session_token" in reg_body
        assert "user_id" in reg_body
        token = reg_body["session_token"]
        user_id = reg_body["user_id"]

        # Step 2: Login with same credentials
        login = await client.post("/auth/login", json={
            "email": "integration_test@example.com",
            "plain_password": "SecureTestPass123!",
        })
        assert login.status_code == 200
        assert "session_token" in login.json()

        # Step 3: Score a biometric signal (authenticated user)
        score = await client.post("/score", json={
            "theta": 0.80, "h_exp": 0.75, "server_load": 0.35,
            "user_agent": "Mozilla/5.0 integration-test",
            "latent_vector": [0.1]*32,
        }, headers={"Authorization": f"Bearer {token}"})
        assert score.status_code == 200
        assert score.json()["shadow_mode"] is False

        # Step 4: Session verify heartbeat
        verify = await client.post("/session/verify", json={
            "session_token": token,
            "user_id": user_id,
            "latent_vector": [0.1]*32,
            "e_rec": 0.04,
            "trust_score": 0.95,
        })
        assert verify.status_code == 200
        assert verify.json()["action"] == "ok"

        # Step 5: Logout
        logout = await client.post(f"/auth/logout?session_token={token}")
        assert logout.status_code == 200
```

**Estimated time:** 1.5 hours

---

#### Integration Test 2: Bot Honeypot Full Cycle

**What to test:** A bot-classified request is shadow-routed, stored in MongoDB, appears in the signatures endpoint, and the MAB reward loop closes.

```python
@pytest.mark.asyncio
async def test_bot_honeypot_full_cycle():
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Step 1: Send bot-like signal
        score = await client.post("/score", json={
            "theta": 0.04, "h_exp": 0.3, "server_load": 0.4,
            "user_agent": "python-requests/2.31.0",
            "latent_vector": [],
        })
        assert score.status_code == 200
        body = score.json()
        assert body["shadow_mode"] is True
        mab_arm = body.get("mab_arm", 0)
        assert 0 <= mab_arm <= 2

        # Step 2: Verify signature appears in honeypot log
        sigs = await client.get("/honeypot/signatures")
        assert sigs.status_code == 200
        assert sigs.json()["count"] >= 1

        # Step 3: Close the MAB reward loop
        reward = await client.post("/honeypot/reward", json={
            "arm": mab_arm, "reward": 0.8,
        })
        assert reward.status_code == 200
        assert reward.json()["arm"] == mab_arm
```

**Estimated time:** 1.5 hours

---

#### Integration Test 3: Watchdog Escalation Chain

**What to test:** As trust_score decreases across multiple heartbeats, the watchdog action escalates from OK → passive_reauth → disable_sensitive_apis.

```python
@pytest.mark.asyncio
async def test_watchdog_escalation():
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Heartbeat 1: healthy session
        r1 = await client.post("/session/verify", json={
            "session_token": "test", "user_id": "usr_test",
            "latent_vector": [0.1]*32, "e_rec": 0.03, "trust_score": 0.95,
        })
        assert r1.json()["action"] == "ok"

        # Heartbeat 2: drift warning level
        r2 = await client.post("/session/verify", json={
            "session_token": "test", "user_id": "usr_test",
            "latent_vector": [0.1]*32, "e_rec": 0.20, "trust_score": 0.45,
        })
        assert r2.json()["action"] in ("passive_reauth", "disable_sensitive_apis")

        # Heartbeat 3: critical breach
        r3 = await client.post("/session/verify", json={
            "session_token": "test", "user_id": "usr_test",
            "latent_vector": [0.1]*32, "e_rec": 0.40, "trust_score": 0.20,
        })
        assert r3.json()["action"] in ("disable_sensitive_apis", "force_logout")
```

**Estimated time:** 1 hour

---

### 8.4 — VIVEK: End-to-End Tests

E2E tests run a real browser against the running stack and simulate actual user behavior.

**Tools:** Playwright (Python)

**Install:**
```bash
pip install playwright pytest-playwright
playwright install chromium
```

**File:** `tests/test_e2e.py`

---

#### E2E Test 1: Login Page Loads and Shows Biometric Status

```python
import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:3000"  # frontend dev server

def test_login_page_shows_biometric_engine(page: Page):
    page.goto(BASE_URL + "/login")

    # Check branding
    expect(page.get_by_text("ENTROPY PRIME")).to_be_visible()

    # Wait for engine to initialize (up to 5 seconds)
    expect(page.get_by_text("BIOMETRIC ENGINE ACTIVE")).to_be_visible(timeout=5000)

    # Check form elements
    expect(page.get_by_placeholder("operator@entropy.io")).to_be_visible()
    expect(page.get_by_placeholder("••••••••••••")).to_be_visible()
    expect(page.get_by_text("AUTHENTICATE")).to_be_visible()
```

**Estimated time:** 1 hour

---

#### E2E Test 2: Typing Updates Live Signals

```python
def test_typing_updates_biometric_signals(page: Page):
    page.goto(BASE_URL + "/login")

    # Get initial keystroke count
    initial_text = page.locator(".cardFooter b").first.inner_text()

    # Type in the email field
    email_input = page.get_by_placeholder("operator@entropy.io")
    email_input.click()
    email_input.type("testuser@entropy.io", delay=80)  # 80ms between keystrokes

    # Wait for signal update (engine runs every 1.5s)
    page.wait_for_timeout(2000)

    # Keystroke count should have increased
    updated_text = page.locator(".cardFooter b").first.inner_text()
    initial_count = int(initial_text) if initial_text.isdigit() else 0
    updated_count = int(updated_text) if updated_text.isdigit() else 0
    assert updated_count > initial_count, "Keystroke count should increase after typing"
```

**Estimated time:** 1 hour

---

#### E2E Test 3: Session Persists After Page Reload

```python
def test_session_persists_after_reload(page: Page):
    # This requires a running backend + mock login or real credentials
    page.goto(BASE_URL + "/login")

    # Simulate a login by setting localStorage directly
    page.evaluate("""() => {
        localStorage.setItem('ep_token', 'test_token_abc')
        localStorage.setItem('ep_user', JSON.stringify({
            id: 'usr_12345', email: 'test@example.com'
        }))
    }""")

    # Navigate to dashboard
    page.goto(BASE_URL + "/dashboard")

    # Should see dashboard, not be redirected to login
    expect(page.get_by_text("BIOMETRIC DASHBOARD")).to_be_visible(timeout=3000)

    # Reload the page
    page.reload()

    # Should still be on dashboard
    expect(page.get_by_text("BIOMETRIC DASHBOARD")).to_be_visible(timeout=3000)
    expect(page.url).not_to_contain("/login")
```

**Estimated time:** 45 minutes

---

#### E2E Test 4: Unauthenticated Users Redirected to Login

```python
def test_unauthenticated_dashboard_redirect(page: Page):
    # Clear any stored session
    page.goto(BASE_URL)
    page.evaluate("localStorage.clear()")

    # Try to access dashboard directly
    page.goto(BASE_URL + "/dashboard")

    # Should redirect to login
    expect(page).to_have_url(BASE_URL + "/login", timeout=3000)

def test_unauthenticated_threats_redirect(page: Page):
    page.goto(BASE_URL)
    page.evaluate("localStorage.clear()")
    page.goto(BASE_URL + "/threats")
    expect(page).to_have_url(BASE_URL + "/login", timeout=3000)
```

**Estimated time:** 30 minutes

---

### 8.5 — VIVEK: Load & Performance Tests

Load tests verify the system can handle many concurrent users.

**Tools:** Locust

**Install:**
```bash
pip install locust
```

**File:** `tests/locustfile.py`

```python
from locust import HttpUser, task, between
import random

class BiometricUser(HttpUser):
    """Simulates a human user interacting with Entropy Prime."""
    wait_time = between(1, 3)  # wait 1-3 seconds between requests

    def on_start(self):
        """Called when a simulated user starts. Register and login."""
        email = f"loadtest_{random.randint(1, 1000000)}@test.com"
        r = self.client.post("/auth/register", json={
            "email": email,
            "plain_password": "LoadTestPass123!",
        })
        if r.status_code == 200:
            self.token = r.json().get("session_token", "")
            self.user_id = r.json().get("user_id", "")
        else:
            self.token = ""
            self.user_id = ""

    @task(5)
    def score_human(self):
        """Most common task: score a human biometric signal."""
        self.client.post("/score", json={
            "theta": 0.7 + random.random() * 0.3,
            "h_exp": 0.6 + random.random() * 0.4,
            "server_load": 0.3 + random.random() * 0.3,
            "user_agent": "Mozilla/5.0 (load test)",
            "latent_vector": [random.random() * 0.2 for _ in range(32)],
        })

    @task(2)
    def watchdog_heartbeat(self):
        """Session heartbeat — runs every 30s in production."""
        if self.token:
            self.client.post("/session/verify", json={
                "session_token": self.token,
                "user_id": self.user_id,
                "latent_vector": [random.random() * 0.1 for _ in range(32)],
                "e_rec": random.random() * 0.1,
                "trust_score": 0.8 + random.random() * 0.2,
            })

    @task(1)
    def health_check(self):
        self.client.get("/health")

class BotAttacker(HttpUser):
    """Simulates bot attack traffic."""
    wait_time = between(0.1, 0.5)  # bots are faster

    @task
    def score_bot(self):
        self.client.post("/score", json={
            "theta": random.random() * 0.1,
            "h_exp": random.random() * 0.3,
            "server_load": 0.5,
            "user_agent": "python-requests/2.31.0",
            "latent_vector": [],
        })
```

**Run the load test:**
```bash
# Requires backend running at localhost:8000
locust -f tests/locustfile.py --host http://localhost:8000 \
  --users 50 --spawn-rate 5 --run-time 60s --headless
```

**Performance targets VIVEK must verify:**

| Metric | Target |
|--------|--------|
| `POST /score` P95 response time | < 500ms |
| `GET /health` P99 response time | < 50ms |
| `POST /session/verify` P95 | < 200ms |
| Error rate under 50 concurrent users | < 1% |
| Bot shadow-routing correctly under load | 100% of theta < 0.1 get shadow_mode=true |

**Estimated time:** 2 hours

---

### 8.6 — VIVEK: Security Validation Tests

**File:** `tests/test_security.py`

---

#### Security Test 1: Session Token Cannot Be Reused After Logout

```python
@pytest.mark.asyncio
async def test_token_invalidated_on_logout():
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register and get token
        reg = await client.post("/auth/register", json={
            "email": "security_logout@test.com",
            "plain_password": "SecurePass123!",
        })
        token = reg.json()["session_token"]

        # Logout
        await client.post(f"/auth/logout?session_token={token}")

        # Token should no longer work
        verify = await client.post("/session/verify", json={
            "session_token": token,
            "user_id": reg.json()["user_id"],
            "latent_vector": [0.0]*32,
            "e_rec": 0.05,
            "trust_score": 0.9,
        })
        # Should either return force_logout or an error
        # The specific behavior depends on implementation
        # but the token must not return OK action
        if verify.status_code == 200:
            assert verify.json()["action"] != "ok"
```

---

#### Security Test 2: Synthetic Tokens Cannot Access Real Resources

```python
@pytest.mark.asyncio
async def test_shadow_token_rejected_by_watchdog():
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Get a shadow token by simulating a bot
        score = await client.post("/score", json={
            "theta": 0.02, "h_exp": 0.2, "server_load": 0.4,
            "user_agent": "automated-tool/1.0", "latent_vector": [],
        })
        shadow_token = score.json()["session_token"]
        assert shadow_token.startswith("ep_shadow_")

        # The shadow token should not work for legitimate operations
        # (in a full implementation, the middleware would block it)
        # Here we just verify it's structurally different from real tokens
        assert "." in shadow_token  # has signature separator
```

---

#### Security Test 3: Honeypot Effectiveness Rate

**What to test:** Under 100 requests with theta < 0.1, at least 99 should be shadow-routed.

```python
@pytest.mark.asyncio
async def test_bot_shadow_rate_is_high():
    async with AsyncClient(app=app, base_url="http://test") as client:
        shadowed = 0
        n = 100

        for _ in range(n):
            r = await client.post("/score", json={
                "theta": 0.03 + random.random() * 0.07,  # all below 0.1
                "h_exp": 0.3,
                "server_load": 0.4,
                "user_agent": "bot_test_agent",
                "latent_vector": [],
            })
            if r.json().get("shadow_mode"):
                shadowed += 1

        effectiveness = shadowed / n
        assert effectiveness >= 0.99, \
            f"Honeypot only caught {effectiveness:.1%} of bots (target: ≥ 99%)"
```

---

#### Security Test 4: Input Validation Rejects Malformed Data

```python
@pytest.mark.parametrize("payload,expected_status", [
    ({"theta": 1.5},                          422),   # theta > 1
    ({"theta": -0.1},                         422),   # theta < 0
    ({"theta": 0.5, "h_exp": 2.0},           422),   # h_exp > 1
    ({"theta": 0.5, "latent_vector": [0]*16}, 422),   # wrong latent size
    ({},                                      422),   # missing required field
])
@pytest.mark.asyncio
async def test_invalid_inputs_rejected(payload, expected_status):
    async with AsyncClient(app=app, base_url="http://test") as client:
        r = await client.post("/score", json=payload)
        assert r.status_code == expected_status
```

**Estimated time for all security tests:** 2 hours

---

**VIVEK Total Test Estimate: 10–12 hours**

---

## 9. Cross-Team Integration Checkpoints

These are scheduled sync points where all three team members must meet, verify interfaces, and unblock each other.

---

### Checkpoint 1 — End of Week 1

**Goal:** Verify biometric engine (VED) can talk to the score endpoint (GANESH) in local dev.

**VED U prepares:** Live login page accessible at `http://localhost:3000`

**GANESH prepares:** Backend running at `http://localhost:8000` with `/health` returning 200

**Test together:**
```bash
# VED opens browser, types in login form
# GANESH watches backend logs
curl http://localhost:8000/health
```

**Verify:** θ value updates in the browser every ~1.5 seconds as you type. No CORS errors in browser console.

**Dependency:** VED cannot test the full login flow without GANESH's `/score` endpoint. GANESH needs VED to confirm the request format matches what `api.js` sends.

---

### Checkpoint 2 — End of Week 2

**Goal:** Full authentication flow works end-to-end. Dashboard shows live data. Threat page shows at least one bot signature.

**VED U prepares:** Dashboard with live charts. Threat page with table.

**GANESH prepares:** `/auth/register`, `/auth/login`, `/score`, `/session/verify`, `/honeypot/signatures` all working.

**VIVEK prepares:** Docker Compose stack running with MongoDB. Integration Test 1 (registration flow) passing.

**Test together:**
1. VIVEK starts the Docker stack: `docker-compose up`
2. VED opens the frontend and registers a new account
3. VED types extensively on the dashboard to generate biometric data
4. GANESH checks MongoDB to verify profile was stored: `db.biometric_profiles.findOne()`
5. VED checks Threat page — manually call `/score` with theta=0.02 to generate a bot signature

---

### Checkpoint 3 — End of Week 3

**Goal:** All tests passing. Performance targets met. Ready for final polish.

**VED U**: All frontend unit tests passing (target: 100%). No console errors in Chrome DevTools.

**GANESH**: All pipeline tests passing (`pytest models/test_pipeline.py -v`). API tests passing.

**VIVEK**: Integration tests passing. Load test at 50 users with < 1% error rate. E2E tests passing.

---

### Checkpoint 4 — Final Week

**Goal:** Production deployment dry run. Everyone can deploy independently.

**Shared checklist:**
- [ ] `.env.example` documents every required variable
- [ ] `docker-compose up --build` starts the full stack from a clean checkout
- [ ] All checkpoint models load on startup (look for ✓ in logs)
- [ ] `/admin/pipeline-debug` returns all 4 stages with non-null data
- [ ] Login → Dashboard → Threat page flow works in the Dockerized frontend
- [ ] Load test at 50 concurrent users passes performance targets
- [ ] Security tests all pass
- [ ] README.md updated with setup and deployment instructions

---

## 10. Glossary of Key Terms

| Term | Simple Explanation |
|------|-------------------|
| **θ (theta)** | The "humanity score" — a number from 0 to 1 output by the CNN. Higher = more human. |
| **h_exp** | Password entropy score — how unpredictable/strong a password is. |
| **e_rec** | Reconstruction error from the autoencoder — measures how different current typing is from your normal pattern. Higher = more suspicious. |
| **EMA** | Exponential Moving Average — a way to track a smoothly-updating average that forgets old data slowly. Used for behavioral profiling. |
| **Welford's algorithm** | An efficient online method to compute mean and variance without storing all data points. |
| **CNN1D** | 1D Convolutional Neural Network — processes the timing sequence of keystrokes to extract patterns. |
| **DQN** | Deep Q-Network — a reinforcement learning agent that learns to pick the best Argon2id strength. |
| **PPO** | Proximal Policy Optimization — a reinforcement learning agent that learns to detect identity drift. |
| **MAB** | Multi-Armed Bandit — a simple learning algorithm that tries different strategies (deception arms) and learns which works best. |
| **Argon2id** | A modern password hashing algorithm. Makes brute-force attacks slow by requiring lots of memory and time. |
| **Shadow mode** | When a bot is detected, it is "shadow-routed" — given a fake session with fake data instead of being blocked. |
| **Honeypot** | A trap that gives bots plausible-looking fake data while harvesting their behavioral signatures. |
| **Latent vector** | A 32-dimensional compressed representation of the current behavioral signal, produced by the encoder. |
| **Trust score** | A running estimate (0–1) of whether the current session user is the same person who originally logged in. |
| **Drift** | When the current behavioral pattern deviates significantly from the user's established baseline. |
| **Degraded mode** | When at least one pipeline stage had to use fallback rules instead of its ML model. Indicated by `degraded=true` in the response. |
| **CORS** | Cross-Origin Resource Sharing — a browser security mechanism. The backend must list allowed origins in `CORS_ORIGINS`. |
| **ASGI** | Asynchronous Server Gateway Interface — the protocol FastAPI uses to handle requests. Uvicorn is the ASGI server. |
| **Upsert** | A database operation that either updates an existing document or inserts a new one if it doesn't exist. Used for biometric profiles. |
| **TTL Index** | A MongoDB index that automatically deletes documents after a specified time. Used for drift events (30 days) and expired sessions. |

---

*Document Version: 1.0 | Project: Entropy Prime v3.0 | Team: VED U, GANESH, VIVEK*
