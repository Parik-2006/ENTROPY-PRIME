# ENTROPY-PRIME
│   │
│   ├── pages/
│   │   ├── LoginPage.jsx     ← Phase 1+2: biometric login with live signals
│   │   ├── LoginPage.module.css
│   │   ├── DashboardPage.jsx ← Phase 4: live θ/E_rec charts + session watchdog
│   │   ├── DashboardPage.module.css
│   │   ├── ThreatPage.jsx    ← Phase 3: honeypot signature viewer
│   │   └── ThreatPage.module.css
│   │
│   ├── services/
│   │   ├── biometrics.js     ← TF.js: 1D-CNN, Autoencoder, collectors
│   │   └── api.js            ← all fetch calls to FastAPI
│   │
│   └── context/
│       └── AuthContext.jsx   ← global auth state + watchdog heartbeat
│
├── backend/
│   ├── main.py               ← FastAPI: all 4 phases + CORS
│   ├── train.py              ← DQN offline pre-trainer
│   └── requirements.txt
│
├── package.json
└── vite.config.js            ← proxies /api → localhost:8000
```

---

## The Four Phases

### Phase 1 — Biological Gateway  *(browser)*
`KeyboardCollector` captures **dwell time** (key-down → key-up) and **flight
time** (key-up → next key-down) at `performance.now()` precision.
`PointerCollector` captures velocity, acceleration, and **neuromuscular
jitter** (high-frequency micro-oscillation magnitude between frames).

A **1D-CNN** (`Conv1D 32 → Conv1D 64 → GlobalMaxPool → Dense → Sigmoid`)
maps a 50-frame window of these signals to **θ ∈ [0,1]** (humanity score).

`computeExpectationEntropy()` applies Zipf's law to the password string,
producing **H_exp ∈ [0,1]** (randomness score).

### Phase 2 — Resource Governor  *(backend)*
A **DQN agent** observes `[θ, H_exp, server_load]` and selects an Argon2id
preset. Asymmetric reward: +2.0 for correctly crushing a bot with HARD params,
−2.0 for giving a bot cheap params. Each auth attempt is an online training
transition fed into the replay buffer.

| Preset   | Memory  | Time | Threads | Approx. latency |
|----------|---------|------|---------|-----------------|
| Economy  | 64 MB   | 2    | 4       | ~120 ms         |
| Standard | 128 MB  | 3    | 4       | ~350 ms         |
| Hard     | 512 MB  | 4    | 8       | ~1.4 s          |
| Punisher | 1024 MB | 8    | 16      | ~9 s            |

### Phase 3 — Offensive Deception  *(backend)*
θ < 0.1 → HTTP 200 with a **synthetic session token** (`ep_shadow_…`).
The bot never knows it was caught. Every subsequent request from that token
is logged to the honeypot signature store, visible in the **Threat Intel** page.

### Phase 4 — Session Watchdog  *(browser + backend)*
Post-login, a **deep autoencoder** (128→64→32→64→128) anchors a 60-second
identity baseline as a latent vector. Every 30 seconds, reconstruction error
**E_rec** is computed. If E_rec > 0.18, trust score decays; below 0.5 triggers
passive re-auth; below 0.25 silently disables sensitive API endpoints.

---

## Manual Setup (without start.sh)

### Backend
```bash
cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt

# Optional: pre-train the RL governor (~2 min)
python train.py --episodes 100000 --out ../checkpoints/governor.pt
export EP_RL_CHECKPOINT=../checkpoints/governor.pt

# Start
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
npm install
npm run dev        # → http://localhost:3000
```

---

## Environment Variables

| Variable             | Default   | Purpose                                 |
|----------------------|-----------|-----------------------------------------|
| `EP_SESSION_SECRET`  | random    | HMAC key for real session tokens        |
| `EP_SHADOW_SECRET`   | random    | HMAC key for synthetic honeypot tokens  |
| `EP_RL_CHECKPOINT`   | (none)    | Path to pre-trained DQN `.pt` file      |

---

## API Reference

| Method | Path                   | Description                              |
|--------|------------------------|------------------------------------------|
| POST   | `/score`               | Submit θ + H_exp → get token + params   |
| POST   | `/password/hash`       | Hash password with RL-selected Argon2id  |
| POST   | `/password/verify`     | Verify password against stored hash      |
| POST   | `/session/verify`      | Watchdog heartbeat (E_rec + trust score) |
| GET    | `/honeypot/signatures` | Retrieve harvested bot signatures        |
| GET    | `/health`              | Server health + RL step count            |
| GET    | `/docs`                | Auto-generated Swagger UI                |

---

## Privacy Model

```
Browser                              Server
───────────────────────────          ───────────────
Raw keystrokes      ─╮
Raw mouse coords    ─┤  never leave   Only transmitted:
Dwell/flight times  ─┤  the browser   • θ  (1 float)
Velocity/jitter     ─╯               • H_exp (1 float)
                                     • latent vector (32 floats)
```

Raw biometric signals are processed entirely at the edge (browser). The server
only ever receives derived representations — a scalar humanity score, an entropy
score, and a compressed latent identity vector. There is no way to reconstruct
keystroke timings or mouse paths from what the server stores.

---

## Extending the System

**Add real user DB**: Replace the `uid = "usr_" + secrets.token_hex(6)` line in
`/score` with a lookup against your user store, and add a `/login` endpoint that
verifies the password hash before issuing the session token.

**Pre-train the RL policy**: Run `python backend/train.py --episodes 200000`.
The policy starts random but converges to correct asymmetric behaviour in
~50,000 steps. With a checkpoint, action selection is immediately correct.

**Add HTTPS**: Put Nginx in front of uvicorn. The Vite proxy in `vite.config.js`
is for local dev only; in production, set `VITE_API_URL` and point directly at
your API domain.
>>>>>>> bb04dac (Initial commit)
