# Database Connections

> Audit only. Cited to exact files/lines.

## 1. Databases currently wired

| Store | Driver / library | Purpose | Connected from |
|---|---|---|---|
| **MongoDB** | `motor` (async) + `pymongo` | users, sessions, biometric_profiles, drift_events, honeypot, threats | `backend/database.py:58-60, 133` |
| **mongomock_motor** | in-memory fallback | dev/test when no real Mongo | `backend/database.py:166-174` |
| **Redis** | (session cache / rate-limit) | optional cache; degrades to DB/allow if absent | `backend/services/redis*.py`, env `REDIS_URI` |
| **Browser localStorage** | Web Storage API | **per-user behavioral baseline** + bank demo state | `src/services/biometrics.js:480-501` |

There is **no SQL database** (no PostgreSQL/SQLite/Supabase). No SQL ORM is used — Mongo
is accessed directly through Motor (document store, not an ORM).

## 2. Connection strings — source

- Mongo URL: `os.environ["MONGODB_URL"]` (default `mongodb://localhost:27017`) and
  `MONGODB_DB_NAME` (default `entropy_prime`) — `backend/database.py:135-136`.
- Defined in `.env` / `.env.example:13-16`:
  ```
  MONGODB_URL=mongodb://entropy:${MONGO_PASSWORD}@mongodb:27017/entropy_prime?authSource=admin
  MONGODB_DB_NAME=entropy_prime
  ```
- Redis: `REDIS_URI` (`.env.example:18`).
- Frontend → backend base URL: `VITE_API_URL` (`.env.example:42`), consumed in
  `src/services/api.js:10`.

## 3. Environment variables used by the data layer

`MONGODB_URL`, `MONGODB_DB_NAME` (database.py); `REDIS_URI`/`REDIS_PASSWORD`,
`MONGO_USER`/`MONGO_PASSWORD` (compose/env); `VITE_API_URL` (frontend).

## 4. Connection behavior (important)

`connect_to_mongo()` (`database.py:133`) retries the real Mongo 5× (`:138`); on failure
it **falls back to `mongomock_motor`** (`:166-174`) — an **in-memory** mock. In that
mode all "persistence" is process-local and **lost on backend restart**. So whether the
profile truly persists server-side depends on a real Mongo being reachable.

## 5. Collections involved

| Collection | Written by | Key fields |
|---|---|---|
| `users` | `create_user` `database.py:495` | email, password_hash, tenant_id, `biometric_profile:{}` |
| `sessions` | `create_session` `:565` | session_token, latent_vector, **trust_score**, expires_at |
| `biometric_profiles` | `upsert_biometric_profile` `:663`, `store_biometric_sample` `:861` | aggregated EMA + state machine |
| `drift_events` | `log_drift_event` `:930` | drift_score, trust_score, e_rec, action |
| `feature_selections` | `record_feature_selection` `:995` | selected_features, means, variances |
| `honeypot` | `store_honeypot_entry` `:1032` | user_agent, theta, ip, path |
| `threat_intelligence` / `threat_broadcasts` | `Database.upsert_threat` `:245` / `:329` | cross-site threat records |
| `tenants` / `sites` | `:426` / `:452` | multi-tenant SaaS |

## 6. `biometric_profiles` — exact schema

Assembled in `upsert_biometric_profile` (`database.py:705-724`) + EMA fields from
`store_biometric_sample` (`database.py:902-921`):

```jsonc
{
  "_id": ObjectId,
  "user_id": "string",
  "tenant_id": "string | null",
  "site_id": "string | null",

  // onboarding state machine
  "onboarding_state": "collecting | syncing | stable | drifted",

  // aggregated profile (upsert_biometric_profile)
  "sample_count": 0,
  "last_drift": 0.0,
  "adaptive_threshold": 1.8,
  "feature_means": [/* floats */],
  "selected_features": ["dwell_norm", ...],
  "ema_profile":  [/* 8 floats | null */],
  "ema_variance": [/* 8 floats | null */],

  // rolling per-channel EMA (store_biometric_sample, ALPHA=0.05)
  "avg_theta": 0.0, "avg_h_exp": 0.0,
  "avg_dwell": 0.0, "avg_flight": 0.0, "avg_speed": 0.0,
  "avg_jitter": 0.0, "avg_accel": 0.0, "avg_rhythm": 0.0,

  "created_at": ISODate, "updated_at": ISODate, "reset_at": ISODate?
}
```

Indexes: `tenant_id`, `site_id`, and compound `(tenant_id, onboarding_state)`
(`database.py:197-203`).

## 7. Is profile data actually persisted?

- **Client localStorage:** **Yes, always** (browser-local, survives reload). This is the
  copy used for live drift.
- **MongoDB:** **Yes if a real Mongo is reachable**; otherwise written to in-memory
  mongomock and lost on restart. Only **aggregated** stats — never raw keystrokes.
