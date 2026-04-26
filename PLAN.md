# ENTROPY PRIME — Full Implementation Plan
## What Each Feature Does (Plain English) + What's Broken + Who Does What

---

## 🧠 What Each Feature Is For (Simple Explanation)

| Feature | What it does in simple words |
|---|---|
| **1D-CNN (Phase 1)** | Watches HOW you type — speed, pauses, rhythm — and gives a "are you human?" score (called θ/theta). A bot types perfectly; a human doesn't. |
| **DQN Governor (Phase 2)** | A smart AI that decides HOW HARD to make your password hashing. If you look like a human → easy/fast hash. If you look like a bot → brutally slow hash that wastes attacker's time. |
| **Honeypot / MAB (Phase 3)** | If the system is 90% sure you're a bot (θ < 0.1), it doesn't block you — it LIES. Gives you a fake session token, fake data, and silently logs everything you do for threat intelligence. |
| **Session Watchdog / PPO (Phase 4)** | Even after login, every 30 seconds it checks: "Is the same person still typing?" If the pattern changes (account takeover / session hijack), it raises an alarm and can log you out. |
| **MongoDB** | Stores real users, real passwords (hashed), sessions, and bot signatures. |
| **Argon2id** | The strongest password hashing algorithm. Like bcrypt but better. The DQN picks how powerful to make it per user. |
| **Autoencoder** | Learns YOUR unique typing fingerprint at login. Later compares live typing to that fingerprint. If too different → suspicious. |
| **MAB (Multi-Armed Bandit)** | Picks the best "deception strategy" to use on bots (which fake data to serve). Learns over time which strategy fools bots longest. |

---

## 🚨 Critical Bugs That Break the Entire Project

### BUG 1 — `backend/requirements.txt` is EMPTY
**Impact:** `pip install -r requirements.txt` installs NOTHING. Backend cannot start.
**Fix:** Fill it with all dependencies (see Section 3).

### BUG 2 — `backend/models/__init__.py` does not exist
**Impact:** Python cannot import `from models.dqn import DQNAgent` etc. Backend crashes on startup.
**Fix:** Create an empty `__init__.py` in `backend/models/`.

### BUG 3 — `/biometric/extract` endpoint has wrong body type
**Impact:** FastAPI tries to read `raw_signal` as a query param, not JSON body. Always 422 error.
**Fix:** Wrap `raw_signal` in a Pydantic model.
```python
# BROKEN:
async def biometric_extract(raw_signal: list[float]):

# FIXED:
class BiometricExtractReq(BaseModel):
    raw_signal: list[float]

async def biometric_extract(req: BiometricExtractReq):
```

### BUG 4 — `/models/dqn/action` and `/models/ppo/evaluate` have wrong body types
**Impact:** Same issue — `state: list[float]` is treated as query param. Always fails.
**Fix:** Use Pydantic models for both.

### BUG 5 — `/auth/logout` accepts `session_token` as query param but frontend sends JSON
**Impact:** Logout always fails — token never found.
**Fix:** Use a Pydantic model to accept it as JSON body.

### BUG 6 — Login page does NOT call `/auth/login` — it calls `/score` instead
**Impact:** Users are never actually authenticated against MongoDB. The whole auth flow is broken — anyone can log in with any email.
**Fix:** `LoginPage.jsx` must call `POST /auth/register` for new users and `POST /auth/login` for existing users, then get the real session token from MongoDB.

### BUG 7 — No `.env` file exists (only `.env.example`)
**Impact:** `MONGODB_URL` is missing → backend falls back to `localhost:27017` which may not be running.
**Fix:** Run `cp .env.example .env` and fill in MongoDB URL before starting.

### BUG 8 — `PPOAgent` has no `select_action` method
**Impact:** If PPO is ever called for action selection, it will crash with `AttributeError`.
**Fix:** Add a `select_action` method to `PPOAgent`.

### BUG 9 — `hmac.new(...)` call uses wrong argument order in `TokenManager`
**Impact:** `hmac.new(key, msg, digestmod)` — this is correct Python 3 syntax so it works, but `hmac.new` is not documented in Python 3. Should use `hmac.new(key, msg, digestmod)`.
**Status:** Actually OK in Python 3 — monitor if issues arise on Python 3.11+.

### BUG 10 — Frontend stores session via localStorage but no real token validation on reload
**Impact:** On page refresh, user is still "logged in" but the server-side session may have expired (30 min TTL). No check is done on app load.
**Fix:** Add a session validation call on `AuthProvider` mount.

---

## 📋 Complete Implementation Checklist

### STEP 1 — Fix `backend/requirements.txt` (CRITICAL — do this first)
```
fastapi==0.111.0
uvicorn[standard]==0.29.0
pydantic[email]==2.7.0
argon2-cffi==23.1.0
torch==2.3.0
numpy==1.26.4
pymongo==4.6.1
motor==3.3.2
python-dotenv==1.0.0
httpx==0.27.0
python-multipart==0.0.9
```

### STEP 2 — Create `backend/models/__init__.py`
Empty file — just needs to exist so Python treats the folder as a package.

### STEP 3 — Fix all broken API endpoints (see Bug 3, 4, 5 above)

### STEP 4 — Fix the authentication flow in frontend

Current broken flow:
```
User clicks Login → calls /score (wrong!) → fake user ID created → "logged in"
```

Correct flow to implement:
```
User clicks Register → calls POST /auth/register → user saved in MongoDB
User clicks Login    → calls POST /auth/login    → password verified → real session token
Page refresh         → calls GET /session/verify  → check if session still valid
User clicks Logout   → calls POST /auth/logout    → session invalidated in MongoDB
```

### STEP 5 — Add `select_action` to PPOAgent
```python
def select_action(self, state):
    with torch.no_grad():
        probs = self.policy(torch.FloatTensor(state).unsqueeze(0))
        return int(torch.argmax(probs).item())
```

### STEP 6 — Create `.env` file
```bash
cp .env.example .env
# Then edit .env with your MongoDB URL
```

### STEP 7 — Fix `BiometricExtractReq` in main.py

### STEP 8 — Add session validation on app load in `AuthContext.jsx`

### STEP 9 — Wire up the biometric latent vector to session creation
When a user logs in, store their initial latent vector as the autoencoder baseline.

### STEP 10 — Pre-train the RL Governor (Optional but recommended)
```bash
cd backend
python train.py --episodes 100000 --out ../checkpoints/governor.pt
```

### STEP 11 — Test all 17 APIs with `test-apis.sh`
```bash
chmod +x test-apis.sh
./test-apis.sh
```

### STEP 12 — Docker setup (for production deployment)
```bash
cp .env.example .env   # fill in secrets
docker-compose up -d
```

---

## 📁 File-by-File Status

| File | Status | Problem |
|---|---|---|
| `backend/requirements.txt` | ❌ BROKEN | Empty — backend won't install |
| `backend/models/__init__.py` | ❌ MISSING | File doesn't exist |
| `backend/main.py` | ⚠️ PARTIAL | 3 endpoint bugs, auth flow not wired |
| `backend/database.py` | ✅ GOOD | Complete, well-written |
| `backend/models.py` | ✅ GOOD | Complete Pydantic models |
| `backend/models/dqn.py` | ✅ GOOD | Works correctly |
| `backend/models/mab.py` | ✅ GOOD | Works correctly |
| `backend/models/cnn1d.py` | ✅ GOOD | Works correctly |
| `backend/models/ppo.py` | ⚠️ PARTIAL | Missing `select_action` method |
| `backend/train.py` | ✅ GOOD | Full DQN training script |
| `backend/Dockerfile` | ✅ GOOD | Will work once requirements.txt fixed |
| `docker-compose.yml` | ✅ GOOD | Complete setup |
| `.env.example` | ✅ GOOD | Template exists |
| `.env` | ❌ MISSING | Must be created by developer |
| `src/services/api.js` | ⚠️ PARTIAL | Missing `/auth/register` and `/auth/login` calls |
| `src/services/biometrics.js` | ✅ GOOD | Complete TF.js biometrics engine |
| `src/context/AuthContext.jsx` | ⚠️ PARTIAL | No session validation on reload |
| `src/pages/LoginPage.jsx` | ❌ BROKEN | Calls wrong endpoints — no real auth |
| `src/pages/DashboardPage.jsx` | ✅ GOOD | Complete UI |
| `src/pages/ThreatPage.jsx` | ✅ GOOD | Complete UI |
| `src/App.jsx` | ✅ GOOD | Routes are correct |
| `vite.config.js` | ✅ GOOD | Dev proxy configured |
| `package.json` | ✅ GOOD | All frontend deps listed |
| `start.sh` | ✅ GOOD | Works once backend is fixed |

---

## 👥 Team Division — 3 People

---

### 👤 MAN 1 — Backend Engineer (Python/FastAPI/MongoDB)
**Owns everything server-side**

**Total estimated time: 8–10 hours**

#### Tasks:

**Priority 1 — Get Backend Running (2 hrs)**
- [ ] Fill `backend/requirements.txt` with all packages listed in Step 1 above
- [ ] Create `backend/models/__init__.py` (empty file)
- [ ] Create `.env` file from `.env.example` and configure MongoDB
  - Option A: Sign up at mongodb.com/atlas (free) and paste connection string
  - Option B: Run `docker run -d -p 27017:27017 mongo:latest`
- [ ] Run `pip install -r requirements.txt` and verify no errors
- [ ] Run `python backend/main.py` — confirm "Connected to MongoDB" message

**Priority 2 — Fix Broken Endpoints (2 hrs)**
- [ ] Fix `/biometric/extract` — wrap `raw_signal` in a `BiometricExtractReq` Pydantic model
- [ ] Fix `/models/dqn/action` — wrap `state` in a `DQNActionReq` Pydantic model
- [ ] Fix `/models/ppo/evaluate` — wrap `state` in a `PPOEvaluateReq` Pydantic model
- [ ] Fix `/auth/logout` — accept `session_token` as JSON body via Pydantic model
- [ ] Add `select_action` method to `backend/models/ppo.py`

**Priority 3 — Verify All 17 APIs Work (2 hrs)**
- [ ] Run `./test-apis.sh` script
- [ ] Fix any remaining errors found by the test script
- [ ] Check MongoDB Atlas or Compass to confirm data is being written:
  - `users` collection has the test user
  - `sessions` collection has a session
  - `honeypot` collection gets entries when theta < 0.1

**Priority 4 — RL Training (2 hrs, optional but nice to have)**
- [ ] Run `python backend/train.py --episodes 100000 --out ../checkpoints/governor.pt`
- [ ] Update `.env` to point to checkpoint: `EP_RL_CHECKPOINT=./checkpoints/governor.pt`
- [ ] Restart backend and verify "RL checkpoint loaded" in logs

**Priority 5 — Docker Deployment (2 hrs)**
- [ ] Test `docker-compose up -d`
- [ ] Verify both MongoDB and backend containers start
- [ ] Run `curl http://localhost:8000/health` to confirm

---

### 👤 MAN 2 — Frontend Engineer (React/JavaScript)
**Owns the browser-side experience and API integration**

**Total estimated time: 8–10 hours**

#### Tasks:

**Priority 1 — Fix the Authentication Flow (3 hrs)**

This is the biggest frontend issue. Right now the login page does NOT call `/auth/register` or `/auth/login`. Fix it:

- [ ] Add `registerUser()` and `loginUser()` functions to `src/services/api.js`:
```javascript
// Add these to api.js:
export async function registerUser({ email, plainPassword }) {
  return req('/auth/register', 'POST', {
    email,
    plain_password: plainPassword,
  })
}

export async function loginUser({ email, plainPassword }) {
  return req('/auth/login', 'POST', {
    email,
    plain_password: plainPassword,
  })
}

export async function logoutUser(sessionToken) {
  return req('/auth/logout', 'POST', { session_token: sessionToken })
}
```

- [ ] Add a Register / Login toggle to `LoginPage.jsx` — two modes:
  - **Register mode**: calls `registerUser()`, then auto-logs in
  - **Login mode**: calls `loginUser()`, gets real session token from MongoDB
  - After successful login, call `submitScore()` to run biometric analysis
  - Call `hashPassword()` to show the Argon2id result

- [ ] Update `AuthContext.jsx` `login()` to store the real `user_id` from the API response (not a fake one)

- [ ] Update `AuthContext.jsx` `logout()` to call `logoutUser(token)` API before clearing localStorage

**Priority 2 — Session Validation on App Load (1 hr)**
- [ ] In `AuthContext.jsx`, on component mount, check if stored token is still valid:
```javascript
useEffect(() => {
  const token = localStorage.getItem('ep_token')
  const user = JSON.parse(localStorage.getItem('ep_user') || 'null')
  if (token && user) {
    // Validate with backend — if fails, auto-logout
    sendWatchdogHeartbeat({ ... }).catch(() => logout())
  }
}, [])
```

**Priority 3 — Fix Biometric Profile Display (2 hrs)**
- [ ] After login, fetch the user's biometric profile from `/biometric/profile/{user_id}`
- [ ] Display it in the Dashboard stat cards (avg theta, avg entropy from MongoDB)
- [ ] The DashboardPage currently shows `user?.hExp` but `hExp` is never stored on the user object — fix this

**Priority 4 — Error Handling and UX Polish (2 hrs)**
- [ ] Show a clear error if backend is unreachable on login page ("Backend offline — start the server")
- [ ] Show loading spinner during all API calls
- [ ] Show a "Register" vs "Login" tab clearly — currently both are one button
- [ ] If user already exists (409 error from `/auth/register`), show "Email taken — try logging in"
- [ ] If wrong password (401 from `/auth/login`), show "Incorrect password"

**Priority 5 — Threat Page Improvements (1 hr)**
- [ ] The threat page shows `sig.ua` but the backend stores `sig.user_agent` — fix field name mismatch
- [ ] Add a "Simulate Bot Attack" button that sends a request with `theta: 0.05` to trigger honeypot

---

### 👤 MAN 3 — ML / DevOps / QA Engineer
**Owns model quality, testing, and deployment pipeline**

**Total estimated time: 8–10 hours**

#### Tasks:

**Priority 1 — Complete the PPO Watchdog (2 hrs)**

The PPO model stub in `backend/models/ppo.py` has no training logic. Add it:

- [ ] Add `select_action(state)` method to `PPOAgent`
- [ ] Add a basic `train_step(states, actions, rewards, old_probs)` method using PPO clip loss
- [ ] Add `compute_advantage(rewards, values, gamma=0.99)` helper
- [ ] Update `backend/models/train_ppo.py` with a realistic simulation:
  - States: [trust_score, e_rec, time_since_login, typing_rate, mouse_speed, ...]
  - Actions: 0=OK, 1=passive_reauth, 2=disable_sensitive_apis
  - Rewards: +1 for correctly keeping session, -2 for missing an actual anomaly

**Priority 2 — Complete the CNN Training Script (2 hrs)**

The `backend/models/train_cnn1d.py` uses random data. Replace with realistic data:

- [ ] Generate synthetic human-like timing data (normal distributions for dwell/flight times)
- [ ] Generate synthetic bot-like timing data (constant/very-low-variance timings)
- [ ] Train CNN to classify human (1) vs bot (0) based on timing sequences
- [ ] Save the model and add a loader to `main.py` to load it at startup
- [ ] Add `POST /models/cnn1d/train` endpoint for online fine-tuning (optional)

**Priority 3 — Integration Testing (2 hrs)**
- [ ] Write a full test script that simulates:
  - A real human logging in (high theta, variable timings) → gets STANDARD hash
  - A bot logging in (low theta, constant timings) → gets PUNISHER hash + honeypot
  - A session takeover (trust score drops after login) → watchdog fires
- [ ] Verify the honeypot entries appear in MongoDB
- [ ] Verify session TTL expiry works (set session to expire in 1 min for testing)
- [ ] Verify MAB arm selection changes over time as rewards are submitted

**Priority 4 — Performance & Load Testing (2 hrs)**
- [ ] Test Argon2id timing for each preset:
  - ECONOMY (64MB, t=2): should take ~100-200ms
  - STANDARD (128MB, t=3): should take ~300-600ms
  - HARD (512MB, t=4): should take ~1-2 seconds
  - PUNISHER (1024MB, t=8): should take ~8-15 seconds
- [ ] Document these numbers in a `PERFORMANCE.md` file
- [ ] Test that high server load (simulate with load=0.9) causes DQN to prefer ECONOMY

**Priority 5 — CI/CD and Documentation (2 hrs)**
- [ ] Create `Makefile` with common commands:
  ```
  make install   → pip install + npm install
  make backend   → start FastAPI
  make frontend  → start Vite
  make train     → run RL training
  make test      → run test-apis.sh
  make docker    → docker-compose up
  ```
- [ ] Update `README.md` with exact steps to run from scratch
- [ ] Add a `CONTRIBUTING.md` describing the 4-phase architecture for new devs
- [ ] Test the full Docker setup end-to-end on a clean machine

---

## 🔄 Dependency Order (Do These in This Order)

```
Day 1:
  MAN 1: Fix requirements.txt + create .env + create __init__.py → backend starts
  MAN 2: Can't test yet — focus on writing the auth service functions
  MAN 3: Focus on improving PPO and CNN training scripts

Day 2:
  MAN 1: Fix the 4 broken endpoints → all 17 APIs return correct responses
  MAN 2: Wire auth functions into LoginPage → register/login flow works
  MAN 3: Run integration tests as MAN 1 fixes endpoints

Day 3:
  MAN 1: RL training + Docker deployment
  MAN 2: Session validation + biometric profile display + UX polish
  MAN 3: Performance testing + documentation + Makefile
```

---

## ✅ Definition of "Project Running as Planned"

When all of the following work:

- [ ] `./start.sh` starts both backend and frontend with no errors
- [ ] `http://localhost:3000` loads the login page
- [ ] Typing on the login page shows the live theta score changing in the signal bars
- [ ] Registering a new email creates a user in MongoDB
- [ ] Logging in with wrong password shows an error
- [ ] Logging in with correct password goes to the dashboard
- [ ] Dashboard shows live theta graph updating every 1.5 seconds
- [ ] Dashboard shows trust score decaying if you stop typing naturally
- [ ] Simulating a bot request (theta < 0.1) creates an entry on the Threat Intel page
- [ ] `./test-apis.sh` shows all 17 APIs returning valid responses
- [ ] `docker-compose up -d` runs the full stack without the frontend

---

## 📦 Final `requirements.txt` (Copy-Paste Ready)

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
pydantic[email]==2.7.0
argon2-cffi==23.1.0
torch==2.3.0
numpy==1.26.4
pymongo==4.6.1
motor==3.3.2
python-dotenv==1.0.0
httpx==0.27.0
python-multipart==0.0.9
```

---

## 🔧 Quick Fix Code Snippets

### Fix 1: `backend/models/__init__.py`
```python
# This file intentionally left empty
# Required for Python to treat this directory as a package
```

### Fix 2: Biometric Extract Endpoint in `main.py`
```python
class BiometricExtractReq(BaseModel):
    raw_signal: list[float]

@app.post("/biometric/extract")
async def biometric_extract(req: BiometricExtractReq):
    try:
        signal_tensor = torch.FloatTensor(req.raw_signal).unsqueeze(0).unsqueeze(0)
        with torch.no_grad():
            features = cnn_model(signal_tensor)
        return {
            "success": True,
            "features": features.squeeze().tolist(),
            "dim": features.squeeze().shape[0]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Fix 3: DQN Action Endpoint in `main.py`
```python
class DQNActionReq(BaseModel):
    state: list[float]

@app.post("/models/dqn/action")
async def dqn_action(req: DQNActionReq):
    if len(req.state) != 3:
        raise HTTPException(status_code=400, detail="State must be 3-dimensional")
    state_array = np.array(req.state, dtype=np.float32)
    action = dqn_agent.select_action(state_array)
    return {"action": int(action), "action_label": ACTION_LABELS[action], "state": req.state}
```

### Fix 4: PPO Evaluate Endpoint in `main.py`
```python
class PPOEvaluateReq(BaseModel):
    state: list[float]

@app.post("/models/ppo/evaluate")
async def ppo_evaluate(req: PPOEvaluateReq):
    if len(req.state) != 10:
        raise HTTPException(status_code=400, detail="State must be 10-dimensional")
    state_tensor = torch.FloatTensor(req.state).unsqueeze(0)
    with torch.no_grad():
        action_probs = ppo_agent.policy(state_tensor)
    probs = action_probs.squeeze().tolist()
    return {
        "state": req.state,
        "action_probabilities": probs,
        "recommended_action": int(np.argmax(probs))
    }
```

### Fix 5: Logout Endpoint in `main.py`
```python
class LogoutReq(BaseModel):
    session_token: str

@app.post("/auth/logout")
async def logout(req: LogoutReq):
    await invalidate_session(db_handler.db, req.session_token)
    return {"success": True, "message": "Logged out successfully"}
```

### Fix 6: Add `select_action` to `backend/models/ppo.py`
```python
def select_action(self, state):
    import numpy as np
    with torch.no_grad():
        state_tensor = torch.FloatTensor(state).unsqueeze(0)
        probs = self.policy(state_tensor)
        return int(torch.argmax(probs).item())
```

### Fix 7: `src/services/api.js` — Add auth functions
```javascript
export async function registerUser({ email, plainPassword }) {
  return req('/auth/register', 'POST', {
    email,
    plain_password: plainPassword,
  })
}

export async function loginUser({ email, plainPassword }) {
  return req('/auth/login', 'POST', {
    email,
    plain_password: plainPassword,
  })
}

export async function logoutUser(sessionToken) {
  return req('/auth/logout', 'POST', { session_token: sessionToken })
}
```

---

*Last updated: April 2026 | Entropy Prime v2.0*
