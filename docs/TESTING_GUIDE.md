# Testing & Inspection Guide

> Audit only — these are **read-only** inspection commands. No code is modified.
> The live behavioral baseline lives in the **browser** (localStorage), so most
> profile inspection is done in the browser DevTools console.

---

## 1. View stored behavioral profiles (browser console)

Open the app, log in, then in DevTools → Console:

```js
// List every stored biometric profile + feature selector
Object.keys(localStorage)
  .filter(k => k.startsWith('ep_bioprofile_') || k.startsWith('ep_featsel_'))
  .forEach(k => console.log(k, JSON.parse(localStorage.getItem(k))))

// Inspect the profile for a specific user id (the id shown in the sidebar/user chip)
const uid = '<USER_ID>'
console.table([JSON.parse(localStorage.getItem('ep_bioprofile_' + uid))])
```

Each profile = `{ emaProfile[8], emaVariance[8], sampleCount, driftHistory[], lastDrift }`
(shape from `UserBehavioralProfile.toJSON()`, `src/services/biometrics.js:173`).

## 2. View collected features live (console logs)

The engine already logs every cycle (no changes needed):
- `[LiveEval] theta=… drift=… samples=…` — `biometrics.js:563`
- `[BehavioralProfile] drift=… sampleCount=…` — `biometrics.js:156`

Filter the console by `LiveEval` or `BehavioralProfile` while typing to watch features
and drift update in real time. Feature order is `FEATURE_NAMES` (`biometrics.js:38`).

## 3. View trust & confidence calculations (console)

```js
// Snapshot the persisted EMA baseline and recompute the live-drift formula by hand
const uid = '<USER_ID>'
const p = JSON.parse(localStorage.getItem('ep_bioprofile_' + uid))
console.log('sampleCount', p.sampleCount, 'lastDrift', p.lastDrift)
console.log('emaProfile', p.emaProfile)
// adaptiveThreshold = mean + 2*std of recent driftHistory (biometrics.js:160)
const h = p.driftHistory || []
const mean = h.reduce((s,v)=>s+v,0)/(h.length||1)
const std  = Math.sqrt(h.reduce((s,v)=>s+(v-mean)**2,0)/(h.length||1))
console.log('adaptiveThreshold ≈', mean + 2*std)
```

Identity-Confidence mapping is in `src/context/TrustContext.jsx` (`driftToConf` +
`baseTarget`). The displayed % and tier are visible in the top-right widget; click it
for Trust Score / Behavior Status / Last Verification / Session Duration.

## 4. View database contents (mongosh)

Only meaningful when a **real** Mongo is running (else it's mongomock in-memory).

```bash
mongosh "$MONGODB_URL"      # or: mongosh mongodb://localhost:27017/entropy_prime

use entropy_prime
db.biometric_profiles.find().pretty()
db.biometric_profiles.findOne({ user_id: "<USER_ID>" })
db.sessions.find({ user_id: "<USER_ID>" }, { trust_score:1, last_verified:1 }).pretty()
db.drift_events.find({ user_id: "<USER_ID>" }).sort({ timestamp:-1 }).limit(20).pretty()
db.feature_selections.find({ user_id: "<USER_ID>" }).pretty()
```

Inspect via the API instead (no Mongo client needed):
```bash
# Session token: in browser console -> localStorage.getItem('ep_token')
TOKEN="<ep_token>"
curl -s http://localhost:8000/me -H "X-Session-Token: $TOKEN"
curl -s http://localhost:8000/admin/models-status
curl -s http://localhost:8000/admin/onboarding-summary
curl -s "http://localhost:8000/biometric/profile/<USER_ID>"
curl -s "http://localhost:8000/biometric/profile/<USER_ID>/status"
curl -s http://localhost:8000/honeypot/signatures
curl -s http://localhost:8000/health
```

## 5. Compare two users

```js
// Browser console — diff two stored baselines feature-by-feature
const A = JSON.parse(localStorage.getItem('ep_bioprofile_<USER_A>')).emaProfile
const B = JSON.parse(localStorage.getItem('ep_bioprofile_<USER_B>')).emaProfile
const NAMES = ['dwell','flight','speed','jitter','accel','rhythm','pause','bigram']
console.table(NAMES.map((n,i)=>({ feature:n, userA:A[i], userB:B[i], delta:(A[i]-B[i]).toFixed(4) })))
```

To compare "you" vs "a different typist" on the **same** account in one sitting: read
`lastDrift` from `[BehavioralProfile]` logs while each person types — the impostor's
drift should exceed the `adaptiveThreshold` computed in §3 (until the EMA adapts).

Mongo side-by-side (real Mongo only):
```bash
mongosh entropy_prime --eval 'db.biometric_profiles.find({}, {user_id:1, ema_profile:1, sample_count:1, onboarding_state:1}).pretty()'
```

## 6. Export one user's profile as JSON

```js
// Browser console — copies the full client baseline to the clipboard
const uid = '<USER_ID>'
copy(JSON.stringify({
  profile:  JSON.parse(localStorage.getItem('ep_bioprofile_' + uid)),
  selector: JSON.parse(localStorage.getItem('ep_featsel_'    + uid)),
}, null, 2))
```

Server copy (real Mongo):
```bash
mongoexport --db entropy_prime --collection biometric_profiles \
  --query '{"user_id":"<USER_ID>"}' --jsonArray --out user_profile.json
```

## 7. Verify the model is actually using stored data

1. **Confirm the baseline is loaded on login:** §1 shows a non-empty `emaProfile` after
   you have enrolled once and reloaded the page (proves localStorage retrieval via
   `loadUserProfile`, `biometrics.js:487`).
2. **Confirm live drift uses it:** type normally → `[BehavioralProfile] drift` stays
   low; type very differently (or hand the keyboard over) → drift rises above the
   adaptive threshold (§3). That proves the comparison is against the stored EMA, not a
   constant.
3. **Confirm what the SERVER uses:** in `backend/main.py:816` the watchdog is called as
   `run_watchdog(latent_vector, e_rec, trust_score)` — it does **not** read
   `biometric_profiles`. The client `behavioral_drift` is only logged
   (`main.py:864`). So server-side trust is **not** comparing against the stored EMA
   profile (see `TRUST_PIPELINE.md`).
4. **Confirm demo vs real:** Settings → Security Simulation buttons set explicit
   overrides in `TrustContext` (`simulate*`); with no override active, the confidence
   you see is the real drift mapping.
