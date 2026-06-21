# Trust Pipeline — End-to-End Trace

> Audit only. Traces: Enrollment → Storage → Retrieval → Comparison → Trust Score →
> Identity Confidence → Verification Modal, naming every file.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ CAPTURE (global, document-level)                                               │
│  KeyboardCollector / PointerCollector   src/services/biometrics.js:196 / :280  │
└───────────────┬──────────────────────────────────────────────────────────────┘
                ▼  buildFeatureVector (8 dims)  biometrics.js:338
┌──────────────────────────────────────────────────────────────────────────────┐
│ ENROLLMENT                                                                     │
│  EnrollPage.jsx  → ep.evaluate / getLatentVector / collector.addSample         │
│  → submitScore (POST /score)  → syncBiometricProfile (POST /biometric/profile) │
│  Server state machine: collecting→syncing→stable  backend/main.py:1324         │
└───────────────┬──────────────────────────────────────────────────────────────┘
                ▼
┌───────────────────────────────┐     ┌──────────────────────────────────────────┐
│ STORAGE (client, authoritative│     │ STORAGE (server, aggregate)               │
│ for live drift)               │     │ Mongo biometric_profiles                  │
│ localStorage ep_bioprofile_*  │     │ upsert_biometric_profile database.py:663  │
│ saveUserProfile biometrics:480│     │ store_biometric_sample   database.py:861  │
└───────────────┬───────────────┘     └──────────────────────────────────────────┘
                ▼  RETRIEVAL: setUser→loadUserProfile  biometrics.js:523 / :487
┌──────────────────────────────────────────────────────────────────────────────┐
│ COMPARISON (the real per-user check)                                          │
│  _liveEval every 1.5s  biometrics.js:546                                        │
│  UserBehavioralProfile.update(featureVec)  biometrics.js:129                    │
│   drift = sqrt( mean_i ((x_i − ema_i)/std_i)² )   ← live vs per-user EMA        │
│  → emits {type:'score', theta, drift} to AuthContext  biometrics.js:568         │
└───────────────┬──────────────────────────────────────────────────────────────┘
                ▼
┌───────────────────────────────┐     ┌──────────────────────────────────────────┐
│ TRUST SCORE (server)          │     │ IDENTITY CONFIDENCE (client UI)           │
│ POST /session/verify (30s)    │     │ TrustContext.jsx                          │
│  main.py:747                  │     │  baseTarget(): if stable →                 │
│  reads DB trust  main.py:784  │     │   driftToConf(liveDrift, adaptiveThreshold)│
│  orchestrator.run_watchdog(   │     │  ceiling = server trust; θ<0.3 caps        │
│   latent, e_rec, trust)       │     │  eased 600ms loop → confidence %           │
│   pipeline/orchestrator.py:194│     │  tiers: GREEN/YELLOW/ORANGE/RED            │
│  → stage4_watchdog + PPO      │     │                                            │
│  persists sessions.trust_score│     │  AuthContext feeds liveDrift/profileStats  │
│  main.py:845                  │     │  AuthContext.jsx:120-214                    │
└───────────────┬───────────────┘     └───────────────┬──────────────────────────┘
                │  (client behavioral_drift only LOGGED, main.py:864)
                ▼                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ VERIFICATION / RE-AUTH                                                         │
│  Server: action passive_reauth/force_logout → AuthContext.anomaly :199          │
│  UI: TrustContext tier → TrustBanner (yellow) / TrustModal (orange/red)         │
│      src/components/TrustGuards.jsx  rendered in src/components/AppShell.jsx     │
│  verifyIdentity() restores confidence (no logout)  TrustContext.jsx             │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Files involved (complete list)

**Capture / engine**
- `src/services/biometrics.js` — collectors, `UserBehavioralProfile` (drift),
  `UserFeatureSelector`, `SessionWatchdog` (e_rec), localStorage persistence.
- `src/services/biometricCollector.js` — sample aggregation for sync payloads.

**Enrollment / flow**
- `src/pages/EnrollPage.jsx` (new), `src/pages/ProfileBuildPage.jsx` (legacy).
- `src/services/api.js` — `submitScore`, `syncBiometricProfile`,
  `sendWatchdogHeartbeat`, `resetBiometricProfile`.

**State / trust**
- `src/context/AuthContext.jsx` — engine boot, profile polling, 30 s heartbeat,
  `anomaly`, `trustScore`, `liveDrift`, `profileStats`.
- `src/context/TrustContext.jsx` — Identity Confidence, tiers, demo simulators,
  history/events.
- `src/components/IdentityConfidence.jsx`, `TrustGuards.jsx`, `TrustTimeline.jsx`,
  `AppShell.jsx`.

**Backend**
- `backend/main.py` — `/score` (`:636`), `/session/verify` (`:747`),
  `/biometric/profile` (`:1324`), `/biometric/profile/reset` (`:1485`), `/me` (`:1112`).
- `backend/pipeline/orchestrator.py` — `run_watchdog` (`:194`).
- `backend/pipeline/stage4_watchdog.py`, `backend/services/watchdog_services.py`.
- `backend/database.py` — all persistence.

## The critical comparison fact

- The **per-user behavioral comparison** (the thing that should distinguish your mother
  from you) happens **client-side** in `UserBehavioralProfile.update`
  (`biometrics.js:129`) against the **localStorage** EMA baseline.
- The **server** `/session/verify` decision uses the client `latent_vector` + `e_rec`
  + DB `trust_score` through PPO (`main.py:816`). It **does not** load the stored
  `biometric_profiles` EMA, and it **ignores** the client `behavioral_drift` except for
  logging (`main.py:864`).
