# Behavioral Profile — Audit

> Status: **audit only**, no code changed. Every claim below is cited to an exact
> file and line in the current codebase.

---

## 1. How enrollment works

Enrollment = building a per-user behavioral baseline by typing naturally until the
profile reaches the **stable** state.

1. The biometric engine (`EntropyPrimeClient`) boots once at app start and attaches
   global listeners to `document` — `src/services/biometrics.js:206` (keyboard
   `start`) and `:280` (pointer). So **all typing/mouse anywhere feeds it**.
   - Bootstrapped in `src/context/AuthContext.jsx:116-138` (`ep.init()`).
2. On login, `ep.setUser(userId)` loads any previously saved per-user profile from
   `localStorage` — `biometrics.js:523-530` → `loadUserProfile()` (`:487`).
3. The enrollment UI is `src/pages/EnrollPage.jsx`. As the user answers prompts, a
   debounced effect (`EnrollPage.jsx:101-150`) calls:
   - `ep.evaluate(text)` → humanity θ + entropy (`biometrics.js:586`)
   - `ep.getLatentVector()` (`:651`)
   - `getBiometricCollector().addSample(...)` (`src/services/biometricCollector.js:43`)
   - `submitScore(...)` → `POST /score`
   - `syncBiometricProfile(payload)` → `POST /biometric/profile` (with
     `requested_state:'stable'` once samples ≥ 50).
4. The server is **authoritative** for the onboarding state machine. The threshold is
   `STABLE_SAMPLE_THRESHOLD = 50` (`backend/database.py:73`). States:
   `collecting → syncing → stable → drifted` (`database.py:64-68`, state machine doc
   `database.py:25-39`).
5. When the sync response returns `onboarding_state = stable`, the client promotes
   itself (`AuthContext.confirmStable`) and Enroll shows "Behavioral Profile
   Established".

> Note: there is **no frozen "enrollment snapshot."** The baseline is a rolling EMA
> that keeps updating during normal use (see §5). This matters for §7 and the Final
> Verdict.

---

## 2. What features are collected

8 normalized channels — `FEATURE_NAMES` at `biometrics.js:38-47`:

| # | Feature        | Meaning                              | Source collector |
|---|----------------|--------------------------------------|------------------|
| 0 | `dwell_norm`   | key press duration                   | KeyboardCollector `biometrics.js:216-233` |
| 1 | `flight_norm`  | inter-key gap                        | KeyboardCollector |
| 2 | `speed_norm`   | pointer speed                        | PointerCollector `:280` |
| 3 | `jitter_norm`  | pointer micro-tremor                 | PointerCollector |
| 4 | `accel_norm`   | pointer acceleration magnitude       | PointerCollector |
| 5 | `rhythm_norm`  | keystroke rhythm consistency (CV)    | KeyboardCollector |
| 6 | `pause_norm`   | long pauses between bursts (>800 ms) | KeyboardCollector `:210-214` |
| 7 | `bigram_norm`  | common bigram dwell ratio            | KeyboardCollector `:224-230` |

The feature vector is assembled by `buildFeatureVector()` (`biometrics.js:338`).
A separate CNN input window (`CNN_SEQ_LEN=50`, `biometrics.js:13`) drives the humanity
score θ and the 32-dim latent vector (`LATENT_DIM=32`).

The richer feature list in the product brief (WPM, backspace rate, error rate, hover
patterns, click frequency, direction changes) is **not currently implemented** — only
the 8 channels above exist. (Listed in the Final Verdict as a gap.)

---

## 3. What metrics are collected / derived

| Metric | Where computed | Notes |
|---|---|---|
| Humanity score **θ** | `ep.evaluate` / `_liveEval` via `CNN1D` (`biometrics.js:546-578, 586`) | 0–1, human-vs-bot |
| Entropy **H_exp** | `computeExpectationEntropy(password)` (`:602`) | password strength |
| 32-dim **latent vector** | `getLatentVector` (`:651`) | fed to autoencoder |
| **Reconstruction error e_rec** | `SessionWatchdog.check` (`:423`) via autoencoder | anomaly signal |
| **Drift** | `UserBehavioralProfile.update` (`:129-158`) | live vs EMA baseline |
| **adaptiveThreshold** | `UserBehavioralProfile.adaptiveThreshold` (`:160-167`) | `mean + 2·std` of recent drift |
| **trust_score** | server PPO/rules in `/session/verify` | persisted in `sessions` |
| Keyboard/pointer aggregate stats | `getKeyboardStats`/`getPointerStats` (`:623-624`) | dwell/flight/speed/jitter |

EMA smoothing coefficient `DRIFT_ALPHA = 0.05` (`biometrics.js:18`); e_rec threshold
`EREC_THRESH = 0.18` (`:16`); per-user selected features `FEAT_K = 6` (`:19`).

---

## 4. Where the metrics are stored

Two independent layers (full detail in `PROFILE_STORAGE.md` and `DATABASE_CONNECTIONS.md`):

- **Client (authoritative for live drift):** per-user EMA profile + feature selector
  serialized to **`localStorage`** — `saveUserProfile()` `biometrics.js:480-485`
  (keys `ep_bioprofile_<userId>` `:477`, `ep_featsel_<userId>` `:478`). Saved every
  15 s (`biometrics.js:542`) and on logout/destroy (`:637-644`).
- **Server (aggregate only):** MongoDB `biometric_profiles` collection — written by
  `upsert_biometric_profile()` (`database.py:663`) + EMA via `store_biometric_sample()`
  (`database.py:861`). **Only aggregated stats are stored; raw keystrokes never leave
  the browser** (`database.py:686, 879`).

---

## 5. When they are updated

| Event | Cadence | Code |
|---|---|---|
| Live eval (θ, drift, feature selection) | every **1.5 s** | `biometrics.js:541` `_evalLoop` → `_liveEval` `:546` |
| Client EMA profile persisted to localStorage | every **15 s** | `biometrics.js:542` `_saveLoop` → `_persistProfile` `:580` |
| Profile stats polled into React state | every **2 s** | `AuthContext.jsx:148-161` |
| Watchdog heartbeat → `/session/verify` | every **30 s** | `AuthContext.jsx:164-214` |
| Aggregated profile → Mongo (`/biometric/profile`) | per debounced keystroke burst during enroll/typing | `EnrollPage.jsx` / `ProfileBuildPage.jsx` |

Because `UserBehavioralProfile.update` advances the EMA on **every** live eval
(`biometrics.js:147-148`), the baseline continuously adapts — including to a different
typist over time.

---

## 6. Which pages collect behavioral samples

Collection is **global** (listeners on `document`), so every authenticated page
contributes. The richest typing surfaces:

- `src/pages/EnrollPage.jsx` — enrollment prompts
- `src/pages/bank/AiBanker.jsx` — chat (primary surface)
- `src/pages/bank/Journal.jsx` — long-form reflection
- `src/pages/bank/Transfers.jsx`, `Beneficiaries.jsx`, `Support.jsx`, `Profile.jsx`
- Legacy: `src/pages/ProfileBuildPage.jsx`, `LoginPage.jsx`

---

## 7. How trust score is calculated

There are **two** distinct trust numbers:

**(a) Server `trust_score`** (persisted in `sessions.trust_score`):
- `/session/verify` (`backend/main.py:747`) reads the **DB** trust as authoritative
  (`main.py:784`), runs `orchestrator.run_watchdog(latent_vector, e_rec, trust_score)`
  (`main.py:816`) → `stage4_watchdog` + PPO. It updates and persists the new score
  (`main.py:845`).
- **Important:** the client-sent `behavioral_drift` is only **logged**
  (`main.py:864-878` `log_drift_event`), *not* used in the decision. The server does
  **not** load the stored per-user EMA profile to compare. Its anomaly signal is the
  autoencoder **e_rec** of the client latent vector + PPO on (e_rec, trust).

**(b) Client `liveDrift`** (the real per-user comparison):
- `UserBehavioralProfile.update` (`biometrics.js:129-158`) computes
  `drift = sqrt( mean_i ((x_i − ema_i)/std_i)² )` of the live feature vector against
  the **per-user EMA baseline** (loaded from localStorage). This is the genuine
  user-specific biometric comparison.

---

## 8. How identity confidence is calculated

`src/context/TrustContext.jsx` derives the always-visible **Identity Confidence %**:
- Once the profile is `stable`, `baseTarget()` maps **real engine drift** to confidence
  via `driftToConf(liveDrift, adaptiveThreshold)` (`TrustContext.jsx` `driftToConf` +
  `baseTarget`). `liveDrift`/`adaptiveThreshold` come from the client
  `UserBehavioralProfile` (§7b) through `AuthContext`.
- The server `trust_score` acts as a ceiling; low humanity θ caps it.
- Before `stable`, confidence = `trustScore·100` (≈100 during enrollment).
- A smoothing loop eases the displayed value toward target each 600 ms with mild
  jitter when green (so it visibly "lives").
- **Demo simulators** (`simulateSlowTypist/FastTypist/DifferentUser/Attacker`) are
  explicit overrides that set a target floor — clearly separate from real detection.

Tier bands: GREEN ≥85 · YELLOW 65–85 · ORANGE 40–65 · RED <40 (`TrustContext.TIERS`).

---

## 9. How re-authentication is triggered

Two paths converge on the same UX:

1. **Server-driven (organic, real):** `/session/verify` returns
   `passive_reauth`/`force_logout` (suppressed to passive while not `stable`,
   `main.py:822-835`). `AuthContext` sets `anomaly` (`AuthContext.jsx:199-208`).
   `TrustContext` watches `anomaly` and drops confidence into the deviation band.
2. **Confidence-driven (UI):** when Identity Confidence enters ORANGE → the verification
   modal (`src/components/TrustGuards.jsx` `TrustModal`); RED → block + re-auth. Both
   render globally from `AppShell` and overlay the app until verified.

`verifyIdentity()` (TrustContext) clears the override and restores confidence (no full
logout, per spec); RED also offers full re-login.

---

## Final Verdict (see also STEP 5 in the chat report)

1. **DB connected?** MongoDB via Motor; falls back to **mongomock (in-memory)** if no
   real Mongo is reachable (`database.py:133-177`). So persistent only when a real
   Mongo is running.
2. **Profile persisted?** Yes — client EMA baseline in **localStorage** (always);
   aggregated EMA in Mongo `biometric_profiles` (if real Mongo). Raw never stored.
3. **Live comparison uses persisted data?** The **client** comparison uses the
   localStorage-backed per-user EMA baseline (real). The **server** watchdog does **not**
   load the stored EMA — it uses client latent/e_rec + DB trust via PPO.
4. **Trust genuinely biometric?** Client drift→confidence: **yes** (real features vs
   per-user EMA). Server trust: real but generic (autoencoder e_rec), not per-user EMA.
   Demo simulators are explicit, non-biometric overrides.
5. **Missing for robust user-vs-user:** frozen enrollment baseline (EMA currently
   self-adapts to impostors), **server-side** authoritative comparison against the
   stored profile (don't trust client-sent drift/e_rec), richer features (WPM/backspace/
   error/hover), and a real persistent DB in the demo environment.
