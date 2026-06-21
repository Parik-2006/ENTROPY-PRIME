# Entropy Prime — Project Structure

> Snapshot after Phase 5. Generated, vendored, and backup directories
> (`node_modules/`, `.venv*/`, `backend/venv/`, `*/__pycache__/`, `.pytest_cache/`,
> `dist/`, `output/`, `migration_backup/`) are omitted for clarity.

## Top-level

```
ENTROPY PRIME/
├── framework/                 ★ NEW — the product surface (engines, gateway, SDKs)
├── examples/                  ★ NEW — demos + integration examples
├── backend/                     FastAPI app + ML + data layer (canonical impl)
├── src/                         React SPA (UNCHANGED) — now an example consumer
├── frontend/honeypot-ui/        Separate TS honeypot decoy UI (UNCHANGED)
├── public/sdk/                  bundled JS SDK artifact (entropy.js)
├── nginx/  mongo/  docs/  scripts/  checkpoints/
├── legacy/   ★ NEW (empty + README; relocation target, Phase 7)
├── archive/  ★ NEW (empty + README; experimental snapshots, Phase 7)
├── migration_backup/  ★ NEW — pre-migration snapshot of backend/ + src/services/
├── MIGRATION_LOG.md           ★ NEW — change ledger
├── FRAMEWORK_ARCHITECTURE.md  ★ NEW — architecture doc
├── PROJECT_STRUCTURE.md       ★ NEW — this file
├── docker-compose{,.dev,.prod}.yml, Dockerfile      (UNCHANGED)
├── package.json, vite.config.js, index.html         (UNCHANGED — SPA)
└── README.md, start.sh, start.bat, run-*.bat        (UNCHANGED)

  Pre-existing duplicates/legacy still in place (classified, NOT yet moved):
   App.tsx · main.tsx · DecoyRenderer.ts · FakeTerminal.tsx · FakeVault.tsx
   · ShadowDashboard.tsx · honeypotClient.ts · useHoneypot.ts · types.ts   (root stray *.tsx)
   new files/ · backend/main_redis_patch.py · backend/models.py            (LEGACY/DUPLICATE)
```

## framework/ (NEW)

```
framework/
├── __init__.py                       version, package docstring
├── shared/__init__.py                contracts, enums, thresholds, onboarding FSM
├── cadence_engine/__init__.py        PHASE 1 facade → stage1 + CNN1D
├── dms_engine/__init__.py            PHASE 2 facade → stage3 + DQN + PPOPolicyAgent
├── honeypot_engine/__init__.py       PHASE 3 facade → stage2 + MAB
├── continuous_auth_engine/__init__.py PHASE 4 facade → stage4 + PPOAgent + WatchdogService
├── intelligence_engine/__init__.py   threat intel + notifications + webhooks
├── orchestrator/__init__.py          PipelineOrchestrator (EngineSequencer)
├── storage/__init__.py               MongoDB + Redis access
├── models/README.md                  model registry + checkpoint provenance
├── integrations/README.md            (placeholder; Phase 5b adapters)
├── api_gateway/                      [Phase 4 — IMPLEMENTED]
│   ├── __init__.py                   build_v1_routers()
│   ├── _clone.py                     faithful route mirroring
│   ├── README.md
│   └── routers/
│       ├── __init__.py
│       ├── auth.py    score.py    session.py    biometric.py
│       └── honeypot.py admin.py   integration.py health.py
└── sdk/                              [Phase 5 — IMPLEMENTED]
    ├── README.md
    ├── js/
    │   ├── entropy-prime.js          browser SDK (fetch + collector)
    │   ├── package.json
    │   └── README.md
    └── python/
        ├── entropy_prime/__init__.py
        ├── entropy_prime/client.py   stdlib REST client
        ├── pyproject.toml
        └── README.md
```

## examples/ (NEW)

```
examples/
├── __init__.py  _bootstrap.py  _simulation.py  _common.py  README.md
├── captcha_bypass_demo/      demo.py  README.md   (DEMO 1)
├── legit_user_demo/          demo.py  README.md   (DEMO 2)
├── different_human_demo/     demo.py  README.md   (DEMO 3)
├── human_variability_demo/   demo.py  README.md   (DEMO 4)
├── bot_detection_demo/       demo.py  README.md   (DEMO 5)
└── integration_minimal/      app.py (Py SDK)  index.html (JS SDK)  README.md
```

## backend/ (canonical implementation — only main.py changed)

```
backend/
├── main.py                    ★ MODIFIED (+20 lines: guarded /v1 mount at EOF)
├── database.py  webhooks.py   (unchanged)
├── middleware/auth.py         (unchanged)
├── models/                    contracts, cnn1d, dqn, mab, ppo, ppo_agents,
│                              stage1-4, pydantic_models, train_*  (unchanged)
├── pipeline/                  orchestrator + stage1-4 shims        (unchanged)
├── services/                  auth, biometric, governor, watchdog,
│                              redis, session_cache, rate_limiter,
│                              notification                          (unchanged)
├── certs/                     jwt_*.pem  (unchanged; security track item)
└── tests/                     pytest stage tests                    (unchanged)
```

## Change summary

| Category | Count | Detail |
|---|---|---|
| Existing files modified | **1** | `backend/main.py` (+20 lines, additive) |
| New top-level dirs | 5 | `framework/ examples/ legacy/ archive/ migration_backup/` |
| New docs | 3 | `MIGRATION_LOG.md`, `FRAMEWORK_ARCHITECTURE.md`, `PROJECT_STRUCTURE.md` |
| Files deleted / moved | **0** | nothing deleted; duplicates classified in place |
| Frontend (`src/`, `frontend/`) changes | **0** | SPA untouched |
| Git operations performed | **0** | all changes local to the workspace |

## How to run — see the run guide in `MIGRATION_LOG.md` and `examples/README.md`

- Backend:  `cd backend && uvicorn main:app --reload --port 8000`  (or `start.bat`)
- Frontend: `npm run dev`  → http://localhost:3000
- Framework: `python -c "import framework; ..."` (facade) — see `FRAMEWORK_ARCHITECTURE.md`
- Demos:    `python examples/<name>_demo/demo.py`  (offline, no server needed)
```
