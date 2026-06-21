# Phase D.1 — Shadow Mode: Testing & Evidence Guide

> **Validation only.** This phase adds a *frozen* enrollment baseline and a
> *server-side* behavioral comparison that is **logged but never acted on**. PPO,
> watchdog decisions, trust score, UI confidence, and re-authentication are
> unchanged — the app behaves identically. Goal here: collect evidence that the
> server-side comparison distinguishes users.

## What was added (all additive)

| Piece | Location |
|---|---|
| Frozen baseline collection + write-once helper | `backend/database.py` `freeze_enrollment_baseline` / `get_enrollment_baseline` |
| Shadow comparison log collection + helpers | `backend/database.py` `log_biometric_comparison` / `get_biometric_comparisons` |
| Pure comparison (distance/similarity/confidence) | `backend/services/biometric_compare.py` |
| Freeze on `stable` (best-effort) | `backend/main.py` `/biometric/profile` |
| Shadow compare + log (logged only) | `backend/main.py` `/session/verify` |
| Optional `feature_window` on heartbeat | `SessionVerifyReq`, `src/services/api.js`, `src/context/AuthContext.jsx`, `src/services/biometrics.js` (`getFeatureVector`) |

New Mongo collections: **`enrollment_baselines`** (write-once), **`biometric_comparisons`** (shadow log).

How the data flows: the 30 s heartbeat now also sends the current normalized 8-dim
window → `/session/verify` loads the user's **frozen** baseline → computes distance vs
that baseline → writes a row to `biometric_comparisons` and a `[ShadowBiometric]` log
line. The heartbeat's decision/response is untouched.

---

## Pre-req: connection (this machine)

Real Mongo is running (see `docs/MONGO_STATUS.md`): db **`entropy`**.
```bash
# project venv has pymongo 4.6.1
PYBIN=".venv/Scripts/python.exe"
URI="mongodb://mongo_user:****@localhost:27017/entropy?authSource=admin"   # password in backend/run-backend.bat
```
Restart the backend after pulling these changes so the new code + indexes load
(`backend/run-backend.bat`).

---

## 1. Inspect frozen baselines

Enroll a user to **stable** first (complete Behavioral Enrollment). Then:

```bash
.venv/Scripts/python.exe - <<'PY'
import pymongo, json
c = pymongo.MongoClient("mongodb://mongo_user:****@localhost:27017/entropy?authSource=admin")
db = c["entropy"]
for b in db.enrollment_baselines.find():
    print(b["user_id"], "v"+str(b["baseline_version"]), "locked="+str(b["locked"]),
          "n="+str(b["n_samples"]))
    print("  mean:", [round(x,3) for x in b["mean"]])
    print("  std :", [round(x,3) for x in b["std"]])
    print("  features:", b["feature_order"])
PY
```
- A row appearing proves the freeze fired on `stable`.
- Re-syncing does **not** change it (write-once) — re-run after more typing and confirm
  `mean`/`std`/`created_at` are identical. Backend log shows `[DB.EB] Froze enrollment
  baseline v1 user=…` exactly once per user.

## 2. Inspect comparison results

```bash
.venv/Scripts/python.exe - <<'PY'
import pymongo, datetime
c = pymongo.MongoClient("mongodb://mongo_user:****@localhost:27017/entropy?authSource=admin")
db = c["entropy"]
uid = "<USER_ID>"   # from the sidebar user chip, or db.users
rows = db.biometric_comparisons.find({"user_id": uid}).sort("ts",-1).limit(40)
print(f"{'time':19} {'dist':>6} {'sim':>6} {'conf':>4} {'tier':>7}  (server action/trust unchanged)")
for r in rows:
    t = datetime.datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{t:19} {r['distance']:6.3f} {r['similarity']:6.3f} {r['confidence']:4d} {r['tier']:>7}  "
          f"{r.get('server_action','?')}/{r.get('server_trust','?')}")
PY
```
You should see rows accruing every ~30 s while a session is open and someone is typing.
`server_action`/`server_trust` are recorded only to prove the live decision did **not**
change with the shadow distance.

Live tail (backend console): filter for `[ShadowBiometric]`.

## 3. Compare Parikshith vs Mother (same account, same device, same session)

This reproduces the headline scenario without logging out.

1. **Parikshith** logs in and completes enrollment → baseline frozen (§1).
2. Keep the session open. **Parikshith types** for ~2 minutes in **AI Banker**
   (`/app/ai`) or **Money Journal** — enough for 3–4 heartbeats.
3. Note the wall-clock time, then hand the keyboard to **Mother**; she types for
   ~2 minutes in the same page, same session.
4. Run the §2 query and read the time-ordered distances:
   - During **Parikshith's** window → `distance` low, `tier` green (high similarity).
   - During **Mother's** window → `distance` rises, `tier` slides to yellow/orange/red.
   The crucial point: it compares against the **frozen** baseline, so Mother is **not**
   absorbed the way the old client EMA would absorb her.

Quick "who typed when" summary (label windows by the times you noted):
```bash
.venv/Scripts/python.exe - <<'PY'
import pymongo, datetime
c = pymongo.MongoClient("mongodb://mongo_user:****@localhost:27017/entropy?authSource=admin")
db = c["entropy"]; uid="<USER_ID>"
# EDIT these ISO times to your test windows:
windows = {
  "Parikshith": ("2026-06-21 14:00:00", "2026-06-21 14:02:00"),
  "Mother":     ("2026-06-21 14:02:30", "2026-06-21 14:04:30"),
}
def ts(s): return datetime.datetime.strptime(s,"%Y-%m-%d %H:%M:%S").timestamp()
rows = list(db.biometric_comparisons.find({"user_id": uid}))
for who,(a,b) in windows.items():
    ds=[r["distance"] for r in rows if ts(a)<=r["ts"]<=ts(b)]
    if ds: print(f"{who:12} n={len(ds):2d} avg_distance={sum(ds)/len(ds):.3f} "
                 f"min={min(ds):.3f} max={max(ds):.3f}")
    else:  print(f"{who:12} no samples in window")
PY
```
Expected: `avg_distance(Parikshith) < avg_distance(Mother)`, ideally by a clear margin.

## 4. Compare Parikshith vs Father

Identical protocol as §3, substituting **Father** in step 3 and a `"Father"` window in
the summary script. Compare all three average distances — the owner should be lowest.

## 5. Confirm behavior is unchanged (regression check)

- Frontend `npm run build` passes (verified).
- The only request change is an **optional** `feature_window`; when absent the heartbeat
  is byte-identical. The shadow block is wrapped in `try/except` and writes to logs/Mongo
  only — it never mutates `wd`, the trust score, or the `/session/verify` response
  (`server_action`/`server_trust` in the log prove this).
- UI, TrustContext confidence, demo simulators, PPO, and re-auth are untouched.

## Interpreting results (sanity from the unit check)

The pure module was validated directly:

| Window vs baseline(mean 0.5, std 0.1) | distance | similarity | confidence | tier |
|---|---:|---:|---:|---|
| identical (0.50) | 0.00 | 1.000 | 100 | green |
| slight (0.55) | 0.50 | 0.882 | 93 | green |
| moderate (0.68) | 1.80 | 0.198 | 58 | orange |
| different (0.90) | 4.00 | 0.000 | 27 | red |

So a real different-typist window (features several σ from the owner's baseline) lands in
orange/red — exactly the evidence this phase is meant to collect. If real distances are
noisy, that informs the **threshold calibration** to do before Phase D.2 makes anything
authoritative.

> Note: comparison rows only appear when (a) a baseline exists for the user and (b) the
> heartbeat carries a `feature_window` (needs ≥5 recent keystrokes). If you see none,
> confirm the baseline (§1) and that someone is actively typing.
