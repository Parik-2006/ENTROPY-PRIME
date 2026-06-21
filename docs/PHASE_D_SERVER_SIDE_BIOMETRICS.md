# Phase D — Server-Authoritative Behavioral Authentication (Architecture)

> **Design only. No code is changed by this document.**
> Builds on the audited current state (`docs/BEHAVIORAL_PROFILE_AUDIT.md`,
> `docs/TRUST_PIPELINE.md`, `docs/PROFILE_STORAGE.md`). Every reference points at
> real code in the repo today.

---

## 0. Why this phase exists (the gap)

Today the **per-user behavioral comparison runs in the browser** against a
`localStorage` EMA baseline (`src/services/biometrics.js:129` drift vs
`ep_bioprofile_<userId>`), and the **server never compares current behavior against
the stored enrollment profile**: `/session/verify` calls
`run_watchdog(latent_vector, e_rec, trust_score)` (`backend/main.py:816`,
`backend/pipeline/orchestrator.py:194`) and only **logs** the client-sent
`behavioral_drift` (`main.py:864`).

Two consequences this design fixes:
1. **Trust is client-trusting.** A modified client can send any `e_rec`/drift.
2. **The baseline self-absorbs impostors.** The EMA updates on every sample
   (`biometrics.js:147`, α=0.05), so a different user is gradually "learned" as
   legitimate — defeating user-vs-user detection.

**Phase D goal:** a *frozen* enrollment baseline + *adaptive* session profile, with
the comparison and trust decision made **server-side and authoritatively**, while
preserving the existing demos, privacy invariant (raw never leaves the browser), and
the PPO/watchdog interfaces.

---

## 1. Frozen enrollment baseline — storage

A **write-once, versioned** statistical signature captured at the
`collecting → stable` transition (sample_count ≥ `STABLE_SAMPLE_THRESHOLD=50`,
`backend/database.py:73`).

- New collection **`enrollment_baselines`** (immutable; never updated by runtime).
- Keyed by `user_id` + `baseline_version` (a new enrollment makes v2, v1 retained for
  audit). The "active" version is referenced from `biometric_profiles`.
- Captured from the same 8-feature space already in use (`FEATURE_NAMES`,
  `biometrics.js:38`): per-feature **mean (μ)**, **std (σ)**, **median**, **MAD**
  (robust), optional **covariance**; plus the per-user **selected features + weights**
  and a calibrated **threshold band**.

Rationale: separating a frozen baseline from the rolling profile is the single change
that enables real user-vs-user detection.

## 2. Adaptive session profile — storage

A short-lived rolling profile **per session**, used for within-session tolerance and
graceful recovery — it must **never** mutate the enrollment baseline.

- New collection **`session_profiles`** (TTL-expired, keyed by `session_token`), or an
  embedded sub-doc on the existing `sessions` document (`database.py:565`).
- Holds a rolling EMA over recent windows, last N window distances, a "session drift"
  estimate, and `last_verified_at`. Reset on explicit verification / step-up.

> Split of responsibility: **enrollment_baselines = identity** (frozen),
> **session_profiles = context** (adapts), **sessions.trust_score = decision** (already
> exists, `database.py:583`).

## 3. Fields to persist from enrollment

```jsonc
// enrollment_baselines (proposed)
{
  "user_id": "string",
  "baseline_version": 1,
  "locked": true,
  "created_at": ISODate,
  "engine_version": "biometrics@<git-sha>",   // for drift-on-model-change
  "feature_order": ["dwell_norm","flight_norm","speed_norm","jitter_norm",
                    "accel_norm","rhythm_norm","pause_norm","bigram_norm"],
  "n_samples": 50,
  "stats": {
    "mean":   [/* 8 */], "std":  [/* 8 */],
    "median": [/* 8 */], "mad":  [/* 8 */]   // robust pair
  },
  "covariance": [/* optional 8x8 or diagonal */],
  "selected_features": ["dwell_norm","flight_norm", ...],   // from UserFeatureSelector
  "feature_weights":   [/* per-feature discriminability, CV-derived */],
  "threshold": { "warn": 1.0, "challenge": 1.5, "block": 2.5 }  // in std units
}
```
Most of this already flows to Mongo today (`ema_profile`, `ema_variance`,
`feature_means`, `selected_features` via `upsert_biometric_profile`,
`database.py:705-724`) — Phase D **snapshots** it once and freezes it.

## 4. Fields that must never adapt

- `enrollment_baselines.stats.*`, `covariance`, `selected_features`,
  `feature_weights`, `threshold`, `feature_order`, `engine_version`.
- The baseline is replaced only by an explicit **re-enrollment** (new version) or
  **reset after re-auth** (`reset_biometric_profile`, `database.py:805`), never by a
  heartbeat. (This is the behavioral fix vs today's `store_biometric_sample` EMA,
  `database.py:861`.)

## 5. Transmitting current behavior to the backend

- Client keeps computing the **aggregated 8-dim window vector** it already produces
  (`buildFeatureVector`, `biometrics.js:338`) over a rolling window (e.g. last
  ~30–50 keystrokes). **Raw keystrokes never transmitted** — preserves the existing
  privacy invariant (`database.py:879`).
- Sent on the existing **30 s heartbeat** by extending `SessionVerifyReq`
  (client `sendWatchdogHeartbeat`, `src/services/api.js:166`) with a
  `feature_window: number[8]` (+ optional `window_robust_stats`). No new endpoint
  required; optionally add `POST /biometric/verify` for higher-frequency checks.
- Anti-spoof: sign/sequence the window, rate-limit (reuse `services/rate_limiter`),
  and have the **server** recompute the distance (don't accept a client distance).

## 6. Backend comparison: current vs enrollment

New pure module **`backend/services/biometric_compare.py`** (keeps `main.py` thin and
respects the facade pattern in `FRAMEWORK_ARCHITECTURE.md`):

```
load active enrollment_baselines[user_id]           # frozen identity
load session_profiles[session_token]                # adaptive context
d_raw   = standardized_distance(window, baseline.stats, weights)   # see §7
d_robust= robust_distance(window, baseline.median, baseline.mad)   # outlier-safe
d       = blend(d_raw, d_robust)
d_sess  = temporal_smooth(d, session_profiles.recent)             # K-window hysteresis
update session_profiles (rolling), persist last distance
return { distance: d_sess, similarity, per_feature_contrib }
```
Key: comparison is **against the frozen baseline**, with the session profile only
providing *tolerance/smoothing* — so a different user cannot be absorbed.

## 7. Similarity score

Reuse the existing, already-trusted drift math so client and server agree
(`biometrics.js:143-150`), but server-authoritative and weighted:

```
z_i  = (x_i - μ_i) / (σ_i + ε)
d    = sqrt( Σ_i w_i · z_i²  /  Σ_i w_i )          # weighted standardized distance
similarity = exp( -d² / 2 )            ∈ (0,1]      # 1 = identical, →0 = far
```
- `w_i` = per-feature discriminability (`feature_weights`, from `UserFeatureSelector`
  CV, `biometrics.js:75-87`).
- Robust variant uses `(x−median)/(1.4826·MAD)`; blend to resist single-window noise.
- Optional full **Mahalanobis** with stored covariance if cross-feature correlation
  matters (diagonal is enough to start).

## 8. Confidence derivation

Map distance → confidence with **hysteresis + temporal smoothing** (no per-window
flapping):

| Distance `d` (std units) | Tier | Confidence band |
|---|---|---|
| ≤ warn (≈1.0) | GREEN Verified | 85–100 |
| warn–challenge (1.0–1.5) | YELLOW deviation | 65–85 |
| challenge–block (1.5–2.5) | ORANGE reduced | 40–65 |
| > block (2.5) | RED not verified | 0–40 |

Rules:
- Require **K consecutive** deviating windows (e.g. 2–3) before a tier drop; recover
  faster than you fall (asymmetric) for good UX.
- **Gate with humanity θ** first: θ < 0.3 (bot) short-circuits to the honeypot/shadow
  path (Phase 3) regardless of distance.
- This mirrors the current client bands (`src/context/TrustContext.jsx` `TIERS`,
  `driftToConf`) so the UI is unchanged — only the **source** moves server-side.

## 9. Integrating with PPO + watchdog

**Constraint to preserve:** the governor uses `PPOPolicyAgent` and the watchdog uses
`PPOAgent` — they are **not interchangeable** (`FRAMEWORK_ARCHITECTURE.md`, "BUG-A").
Do not swap or retrain casually.

Two integration options (recommend **A** first, **B** later):

- **A — Rules pre-gate (no retrain, low risk):** compute an authoritative
  `trust_delta` from biometric `distance` in `biometric_compare`, fold it into the
  `trust_score` that is *fed into* `run_watchdog` (`main.py:816`). PPO still decides the
  action on the combined trust + e_rec. Persist via `update_session_trust_score`
  (`database.py:613`). Map distance tiers → `ok | passive_reauth |
  disable_sensitive_apis | force_logout` exactly as the watchdog already emits.
- **B — Observation augmentation (needs retrain):** add `biometric_distance` as an
  extra feature in the Stage-4 watchdog observation and retrain `PPOAgent`. More
  faithful, but model-risk + checkpoint changes (`EP_PPO_CHECKPOINT`).

Both keep `e_rec` (autoencoder) as a complementary anomaly channel.

## 10. Files that would change

| Layer | File | Change |
|---|---|---|
| DB | `backend/database.py` | + `enrollment_baselines`, `session_profiles` helpers; freeze-on-stable; getters; indexes |
| Compare | `backend/services/biometric_compare.py` *(new)* | distance/similarity/confidence (pure) |
| API | `backend/main.py` | extend `/session/verify` (`:747`); optional `/biometric/verify`; freeze hook in `/biometric/profile` (`:1324`) & reset (`:1485`) |
| Models | `backend/models/pydantic_models.py` | `feature_window` on `SessionVerifyReq`; response fields |
| Watchdog | `backend/pipeline/stage4_watchdog.py` / `services/watchdog_services.py` | consume `trust_delta` (Option A) or new feature (Option B) |
| Client engine | `src/services/biometrics.js` | expose rolling `feature_window`; snapshot baseline on stable |
| Client state | `src/context/AuthContext.jsx` | include `feature_window` in heartbeat |
| Client trust | `src/context/TrustContext.jsx` | consume server `confidence` when available; keep local fallback + demo sims |
| API client | `src/services/api.js` | send window in `sendWatchdogHeartbeat` (`:166`) |

Unchanged on purpose: ML model files, collectors' capture logic, honeypot/DMS,
legacy routes — consistent with prior-phase constraints.

## 11. Migration strategy

1. **Additive + flagged.** New env flag `ENABLE_SERVER_BIOMETRICS` (default `false`).
   New collections only; no destructive schema edits.
2. **Backfill / capture.** On the next `collecting→stable` transition (or a one-off
   backfill job), snapshot the existing `biometric_profiles.ema_profile/ema_variance`
   into `enrollment_baselines` v1 with `locked=true`.
3. **Shadow mode.** Compute server distance/confidence and **log** it alongside the
   current client-driven value (write to `drift_events`, `database.py:930`) without
   changing decisions — validate thresholds against real sessions first.
4. **Cutover.** Flip the flag so server confidence becomes authoritative; client keeps
   a local fallback when no baseline exists.
5. **Versioning.** `baseline_version` + `engine_version` so a future change to
   `buildFeatureVector` invalidates stale baselines gracefully (prompt re-enroll).

## 12. Not breaking existing demos

- Feature flag **off / shadow** by default → current behavior is byte-identical.
- **No baseline yet → fall back** to today's client path (graceful).
- Keep the **demo simulators** (`simulate*` in `TrustContext.jsx`) — route them through
  the same confidence pipeline so judging stays reliable.
- Keep UI tiers/labels identical; only the data source changes.
- Keep all legacy routes/APIs and the onboarding state machine intact.

## 13. Scenario coverage

| Scenario | Detection | Response |
|---|---|---|
| **Same user** | `d` small vs frozen baseline; session smoothing absorbs minor variation | GREEN; gradual recovery after any blip |
| **Different user** | `d` large vs **frozen** baseline (cannot be absorbed); K-window sustained | YELLOW→ORANGE→RED; step-up verify, then block |
| **Bot** | θ<0.3 humanity gate + abnormal timing distribution | Honeypot/shadow (Phase 3) before biometric path |
| **Session takeover** | mid-session distance jump on a still-valid session | `passive_reauth` (no full logout); on verify, reset `session_profiles`, keep enrollment baseline |

The **frozen baseline** is what makes "different user / takeover" detectable where the
current self-adapting EMA fails.

## 14. Mongo schema evolution

- **New** `enrollment_baselines` (§3) — write-once, `{user_id, baseline_version}`
  unique index; `locked`, `engine_version`.
- **New** `session_profiles` — `{session_token}` unique, TTL index on `expires_at`;
  rolling EMA + `recent_distances[]` + `last_verified_at`.
- **Extend** `biometric_profiles` (`database.py:705`): add `active_baseline_version`,
  `is_locked`. Backward-compatible (absent ⇒ pre-Phase-D).
- **Extend** `sessions` (`database.py:574`): add `last_biometric_distance`,
  `last_similarity`. Reuse existing `drift_events` for the audit/shadow log.
- Indexes: `enrollment_baselines (user_id, baseline_version)`; `session_profiles
  (session_token)` + TTL.

## 15. Effort & risk

| Workstream | Effort | Risk | Notes |
|---|---|---|---|
| DB collections + helpers + freeze-on-stable | **S–M** (~1 day) | Low | additive |
| `biometric_compare.py` (distance/conf) | **S** (~0.5 day) | Low | pure, unit-testable |
| `/session/verify` extend + payload | **S** (~0.5 day) | Low–Med | contract change, versioned |
| Client window emit + TrustContext consume | **M** (~1 day) | Med | keep fallback + demos |
| Shadow-mode validation + threshold tuning | **M** (~1–2 days) | Med | needs real sessions |
| PPO Option A (rules pre-gate) | **S** (~0.5 day) | Low | no retrain |
| PPO Option B (retrain w/ new feature) | **L** (days) | **High** | model + checkpoint risk; defer |

**MVP (shadow, Option A): ~3–4 days, Medium risk overall.** Top risks & mitigations:
- *Threshold mis-tuning → false re-auth* → ship in shadow mode, calibrate first;
  asymmetric hysteresis.
- *Client spoofing* → server recomputes distance; sign/rate-limit windows.
- *Privacy regression* → never transmit raw; keep aggregated-only invariant.
- *Model breakage* → prefer Option A; treat `engine_version` change as re-enroll.
- *Demo fragility* → flag default off, simulators preserved, graceful fallback.

---

### One-line summary
Freeze the enrollment baseline in Mongo, keep an adaptive per-session profile, send the
already-computed 8-feature window on the existing heartbeat, compute a weighted
standardized distance **server-side** against the frozen baseline, map it to confidence
with hysteresis, and fold it into the watchdog trust via a rules pre-gate — shipped
behind a flag in shadow mode so current demos are untouched.
