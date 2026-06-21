# ENTROPY PRIME — Framework Migration Log

> Authoritative, append-only record of the restructuring from an application
> layout into a reusable **security framework** layout. **Zero deletions, zero
> git operations.** Every change is reversible via this log and
> `migration_backup/`.

---

## Approved execution parameters

| Decision | Choice |
|---|---|
| Execution mode | Run Phases 0–3 autonomously; **pause for approval before Phase 4 (API gateway) and Phase 6 (Docker)** |
| Container split | In-process now, split-ready (structural only) |
| Security scope | **Structure only — zero behavior change**; security remediation delivered separately |

---

## Phase status

| Phase | Description | Status |
|---|---|---|
| 0 | Safety net (backup + scaffolding) | ✅ Done |
| 1 | Shared spine (`framework/shared`) | ✅ Done |
| 2 | Engine facades (cadence/dms/honeypot/continuous_auth) + orchestrator | ✅ Done |
| 3 | Intelligence + storage facades | ✅ Done |
| 4 | API gateway split (additive /v1 aliases) | ✅ Done |
| 5 | SDK + examples | ✅ Done |
| 6 | Docker reorganization | ⏸ PAUSED — awaiting approval |
| 7 | Physical duplicate relocation into `legacy/`/`archive/` | ⏸ PAUSED — awaiting approval |

---

## Phase 4 — API Gateway split (additive, non-breaking)

**Changed exactly one existing file** (`backend/main.py`): appended a guarded
block at the very end that mounts `/v1` aliases. No original route, handler, or
import was modified or removed.

New files:
```
framework/api_gateway/__init__.py        build_v1_routers()
framework/api_gateway/_clone.py          faithful route mirroring
framework/api_gateway/routers/__init__.py
framework/api_gateway/routers/{auth,score,session,biometric,honeypot,admin,integration,health}.py
```

Mechanism: each `/v1` route is a clone of an existing route that **reuses the
same handler callable** (so dependencies, body models, response models, and
status codes are identical). Verified: 46 original routes intact + 46 `/v1`
mirrors (1:1), OpenAPI builds clean, `POST /score` and `POST /v1/score` resolve
to the same function object. The block is best-effort: if the alias layer fails
to import, the app still starts with the full original route set.

## Phase 5 — SDKs + Examples

New files (all additive):
```
framework/sdk/python/entropy_prime/{__init__,client}.py · pyproject.toml · README.md   (stdlib-only REST client)
framework/sdk/js/entropy-prime.js · package.json · README.md                            (browser SDK)
examples/__init__.py · _bootstrap.py · _simulation.py · _common.py
examples/README.md
examples/integration_minimal/{app.py,index.html,README.md}
examples/{captcha_bypass,legit_user,different_human,human_variability,bot_detection}_demo/{demo.py,README.md}
```

All five demo scenarios run offline (`python examples/<demo>/demo.py`) against
the real framework engines and produce correct, deterministic decisions
(bot→shadow, legit→GREEN, different-human→RED, variability→no false reject).

---

## What Phases 0–3 actually changed

**Additive only.** No existing file was modified, moved, or deleted. A new
top-level `framework/` package was created whose engine modules **re-export**
the canonical implementations from `backend/`. This is provably
behavior-preserving: the running app imports nothing from `framework/`, and
`framework/` imports the exact same objects the app already uses.

### New files created (all new, none overwrite anything)
```
framework/__init__.py
framework/shared/__init__.py
framework/cadence_engine/__init__.py
framework/dms_engine/__init__.py
framework/honeypot_engine/__init__.py
framework/continuous_auth_engine/__init__.py
framework/intelligence_engine/__init__.py
framework/orchestrator/__init__.py
framework/storage/__init__.py
framework/api_gateway/README.md        (placeholder; Phase 4)
framework/sdk/README.md                (placeholder; Phase 5)
framework/integrations/README.md       (placeholder; Phase 5)
framework/models/README.md             (model registry doc)
examples/README.md                     (placeholder; Phase 5)
legacy/README.md
archive/README.md
migration_backup/                       (pre-migration snapshot)
MIGRATION_LOG.md                        (this file)
```

### Backup snapshot (rollback source)
```
migration_backup/backend_pre_migration/      full copy of backend/
migration_backup/src_services_pre_migration/ full copy of src/services/
migration_backup/{index.html,vite.config.js,vite.config.ts,tsconfig.json,package.json}
```

---

## Facade mapping (framework → canonical backend source)

| Framework path | Re-exports (canonical) |
|---|---|
| `framework.shared` | `backend.models.contracts.*`, `backend.models.{OnboardingState,ProfileBuildStatus,STABLE_SAMPLE_THRESHOLD}` |
| `framework.cadence_engine` | `backend.pipeline.stage1_biometric`, `backend.models.cnn1d.CNN1D`, `backend.services.biometric_services` |
| `framework.dms_engine` | `backend.pipeline.stage3_governor`, `backend.models.dqn.DQNAgent`, `backend.models.ppo_agents.PPOPolicyAgent`, `backend.services.governor_services` |
| `framework.honeypot_engine` | `backend.pipeline.stage2_honeypot`, `backend.models.mab.MABAgent` |
| `framework.continuous_auth_engine` | `backend.pipeline.stage4_watchdog`, `backend.models.ppo.PPOAgent`, `backend.services.watchdog_services.WatchdogService` |
| `framework.intelligence_engine` | `backend.services.notification_service`, `backend.webhooks`, `backend.services.watchdog_services` |
| `framework.orchestrator` | `backend.pipeline.PipelineOrchestrator`, `backend.pipeline.BiometricInput` |
| `framework.storage` | `backend.database`, `backend.services.{redis_client,session_cache,rate_limiter}` |

Each engine guards optional heavy imports (torch / motor / httpx) and exposes
an `*_AVAILABLE` flag, so partial environments import cleanly.

---

## File classification (no physical move yet — recorded in place)

Legend: ACTIVE = in the runtime import graph · LEGACY = superseded · DUPLICATE
= copy of a canonical file · EXPERIMENTAL = patch/staging/spec.

### Confirmed DUPLICATE (relocation candidates, Phase 7)
| File / dir | Canonical | Verified |
|---|---|---|
| `/App.tsx, /main.tsx, /DecoyRenderer.ts, /FakeTerminal.tsx, /FakeVault.tsx, /ShadowDashboard.tsx, /honeypotClient.ts, /useHoneypot.ts, /types.ts` | `frontend/honeypot-ui/src/*` | `src/` references none of them (grep clean) |
| `new files/**` | `backend/services/*` + root infra | only referenced as strings in docs |
| `new files/main_redis_patch.py`, `backend/main_redis_patch.py` | merged into `backend/main.py` (v4.0.2) | no code import (grep clean) |
| `backend/scripts/bundle-sdk.sh` | `scripts/bundle-sdk.sh` | identical purpose |
| `new files/docker-compose*.yml` | root `docker-compose*.yml` | staging copies |

### LEGACY (superseded; verify before any move)
| File | Reason |
|---|---|
| `backend/models.py` | Shadowed by the `backend/models/` package; unreachable via import (only `from backend.models import …` resolves, to the package `__init__`). |
| `backend/models/orchestrator.py` | Superseded by `backend/pipeline/orchestrator.py`; only `_CONF_RANK` still consumed (`pipeline/contracts.py`). |
| `backend/services/biometric_service.py` | Singular twin of the imported `biometric_services.py` (plural). Needs content diff before relocation. |
| `backend/Dockerfile-stage1` | Per-stage image experiment; not referenced by any compose file. |

### EXPERIMENTAL (preserve in `archive/` later)
| File / dir | Reason |
|---|---|
| `backend/test_*.py`, `backend/models/test_pipeline.py`, `backend/test_import.py` | Ad-hoc test scripts outside `backend/tests/`. |
| `MD FILES TO BE DONE/**` | Per-developer stage specs + IEEE refs → relocate to `docs/specs/`. |

### NOT a duplicate (correction from initial analysis)
- `index.html` (root) is the **ACTIVE SPA entry** (`<script src="/src/main.jsx">`), not a copy of the honeypot UI's index.

---

## Reversibility / rollback

1. The `framework/`, `legacy/`, `archive/` trees are purely additive — deleting
   them returns the repo to its exact pre-migration state.
2. `migration_backup/` holds byte snapshots of everything that could later be
   physically moved (`backend/`, `src/services/`, key root configs).
3. No file was edited; no git command was run; no history was touched.

---

## Open items requiring approval (Phase 4 / 6 gate)

1. **API-gateway split** of `backend/main.py` into routers (keeping `main:app`
   working + `/v1` aliases).
2. **Docker reorganization** into `deploy/` with split-ready engine boundaries
   and datastore host-port removal.
3. **Physical relocation** of the confirmed DUPLICATE/LEGACY files into
   `legacy/`/`archive/` (currently classified in place only).
