# Profile Storage — Where is the behavioral profile stored?

> Audit only. Direct answer with exact code locations.

## Direct answer

The behavioral profile exists in **two places**, with different roles:

| Layer | Storage | Persistent? | Used for live trust? |
|---|---|---|---|
| **Per-user EMA baseline + feature selector** | **`localStorage`** (browser) | Yes (browser-local) | **YES** — this drives drift/confidence |
| **Aggregated EMA + state machine** | **MongoDB** (`biometric_profiles`), or **mongomock in-memory** if no real Mongo | Mongo: yes · mongomock: no (lost on restart) | No (used for onboarding gate + admin), not the live comparison |

So, against your checklist:

- RAM only — **partly** (working copy is in JS memory; mongomock is RAM-only)
- **localStorage — YES (primary persistence for the live baseline)** ✅
- sessionStorage — no
- IndexedDB — no
- SQLite — no
- PostgreSQL — no
- **MongoDB — YES (aggregated copy, only if a real Mongo is connected)** ✅
- Supabase — no
- Other — Redis (cache only, not the profile)

## Exact code locations

### localStorage (authoritative for live drift)
`src/services/biometrics.js`
```js
const PROFILE_PREFIX  = 'ep_bioprofile_'   // :477
const SELECTOR_PREFIX = 'ep_featsel_'      // :478

export function saveUserProfile(userId, profile, selector) {           // :480
  localStorage.setItem(PROFILE_PREFIX  + userId, JSON.stringify(profile.toJSON()))
  localStorage.setItem(SELECTOR_PREFIX + userId, JSON.stringify(selector.toJSON()))
}
export function loadUserProfile(userId) {                              // :487
  const profileData  = JSON.parse(localStorage.getItem(PROFILE_PREFIX  + userId))
  const selectorData = JSON.parse(localStorage.getItem(SELECTOR_PREFIX + userId))
  return { profile: UserBehavioralProfile.fromJSON(profileData),
           selector: UserFeatureSelector.fromJSON(selectorData) }
}
```
- Written every 15 s and on logout: `biometrics.js:542` (`_saveLoop`), `:580`
  (`_persistProfile`), `:637-644` (`destroy`).
- Loaded on login: `biometrics.js:523-530` (`setUser` → `loadUserProfile`).
- The actual document shape persisted = `UserBehavioralProfile.toJSON()`
  (`biometrics.js:173-181`): `{ emaProfile[8], emaVariance[8], sampleCount,
  driftHistory[], lastDrift }`.

### MongoDB (aggregated copy)
`backend/database.py` — `upsert_biometric_profile` (`:663`) and `store_biometric_sample`
(`:861`). Schema in `DATABASE_CONNECTIONS.md` §6. Reached from
`backend/main.py:1419` (`POST /biometric/profile`). Falls back to mongomock at
`database.py:166-174` when no real Mongo.

## Consequence

Because the live baseline is **localStorage-keyed by `userId`**:
- It is **per-browser**. A different browser/device, or cleared storage, means **no
  baseline** → the engine rebuilds from scratch (no cross-device user-vs-user).
- The server's Mongo copy is **not** consulted for the live drift decision (see
  `TRUST_PIPELINE.md`).
