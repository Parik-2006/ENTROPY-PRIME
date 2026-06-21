# MongoDB Connection Status

> Audit only — live runtime verification. No code modified.
> Captured: 2026-06-21 from this workstation.

## Verdict

**✅ Connected to a REAL MongoDB instance — mongomock fallback is NOT active.**

Evidence:
- An external `pymongo` client connected successfully and `server_info()` returned a real
  server version (**MongoDB 7.0.32**). mongomock is in-process only and cannot be reached
  over a socket, so a successful external TCP connection proves it is a real server.
- Docker container `entropy_mongodb_dev` (`mongo:7.0`) is **Up (healthy)**, publishing
  `0.0.0.0:27017->27017/tcp`.
- The running backend (PID 9784, listening on `:8000`) holds **ESTABLISHED** TCP
  connections to `127.0.0.1:27017`, i.e. it is talking to this real Mongo (mongomock
  would open no sockets).
- The configured Mongo URL is reachable, so the fallback branch at
  `backend/database.py:166-174` (`mongomock_motor`) is never executed.

---

## 1. Active Mongo connection string (password masked)

```
mongodb://mongo_user:****@localhost:27017/entropy?authSource=admin
```

- Source of truth at runtime: `backend/run-backend.bat:18`
  (`set MONGODB_URL=...`), read by `backend/database.py:135`
  (`os.environ.get("MONGODB_URL", ...)`).
- Note: `.env:17` defines a different URL (`...@localhost:27017/entropy?authSource=admin`
  with a placeholder password and db `entropy`). The **batch launcher's** value wins for
  the currently running process. Default if neither is set:
  `mongodb://localhost:27017` (`database.py:135`).

## 2. Database name

```
entropy
```

From `MONGODB_DB_NAME=entropy` (`run-backend.bat:19`; read at `database.py:136`).
(The code default would otherwise be `entropy_prime`.)

## 3. Collection counts (db: `entropy`)

| Collection | Documents |
|---|---:|
| `users` | 4 |
| `sessions` | 18 |
| `biometric_profiles` | **3** |
| `sites` | 1 |
| `tenants` | 1 |
| `threat_intelligence` | 0 |
| `threat_broadcasts` | 0 |

Total: 7 collections. The presence of **3 `biometric_profiles`** documents confirms the
server is genuinely persisting aggregated behavioral profiles to real MongoDB (not an
ephemeral mock). `drift_events`, `feature_selections`, and `honeypot` collections do not
yet exist (no documents written this session).

## 4. Is mongomock active?

**No.** mongomock is the dev fallback used only when the real Mongo is unreachable after
5 retries (`backend/database.py:153-174`). Here the real Mongo is reachable and in use,
so the fallback is not engaged.

| Signal | Observation |
|---|---|
| External pymongo `server_info()` | ✅ real server, v7.0.32 |
| Docker `mongo:7.0` container | ✅ Up (healthy), 27017 published |
| Backend → 27017 sockets | ✅ ESTABLISHED (PID 9784) |
| Fallback branch `database.py:166` | ❌ not executed |

## 5. How this was verified (reproducible, read-only)

```bash
# 1) Is a real mongod running?
docker ps --format '{{.Names}} {{.Image}} {{.Status}} {{.Ports}}' | grep -i mongo
netstat -ano | grep 27017

# 2) Confirm real server + collection counts (project venv has pymongo 4.6.1)
.venv/Scripts/python.exe - <<'PY'
import pymongo
c = pymongo.MongoClient("mongodb://mongo_user:****@localhost:27017/entropy?authSource=admin",
                        serverSelectionTimeoutMS=4000)
print("version", c.server_info()["version"])     # real server → not mongomock
db = c["entropy"]
for name in sorted(db.list_collection_names()):
    print(name, db[name].count_documents({}))
PY
```

> Caveat: this reflects **this machine right now**. If the Docker Mongo is stopped, or the
> backend is started without `run-backend.bat` (so `MONGODB_URL` is unset/unreachable),
> the app will silently fall back to in-memory **mongomock** and these documents will not
> be used. Re-run the steps above to re-verify.
