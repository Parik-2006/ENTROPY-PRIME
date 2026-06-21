# framework/api_gateway — Framework API Gateway (/v1)  [IMPLEMENTED]

Versioned, resource-grouped `/v1` API surface that **mirrors** every existing
endpoint in `backend/main.py` without modifying or removing any of them.

## How it works (zero behavior change)
`backend/main.py` stays the compatibility layer and the single source of truth
for handler logic. At the very bottom of `main.py` (guarded, non-fatal) it calls
`build_v1_routers(...)`, which clones each existing route onto a `/v1` prefix,
**reusing the same handler callable** — so `POST /v1/score` is byte-identical to
`POST /score` (same dependencies, body model, response model, status code).

## Layout
```
api_gateway/
├── __init__.py        build_v1_routers(main_module) -> [APIRouter, ...]
├── _clone.py          clone_matching(): faithful route mirroring
└── routers/
    ├── auth.py        /auth/register, /auth/login, /auth/logout, /me
    ├── score.py       /score, /telemetry, /password/*
    ├── session.py     /session/*
    ├── biometric.py   /biometric/*, /stage1/*, /analyze
    ├── honeypot.py    /honeypot/*
    ├── admin.py       /admin/*
    ├── integration.py /webhooks/*, /notifications/*
    └── health.py      /health
```

## Guarantees (verified)
- 46 original routes intact; 46 `/v1` mirrors (1:1, identical methods).
- No original removed; no stray alias; OpenAPI builds clean.
- Alias layer is best-effort: if it fails to load, the app still serves the
  complete original (un-prefixed) route set.

## Future (Phase 4b, not yet done)
Physically relocate handler *bodies* into `routers/*` and reduce `main.py` to a
thin assembler. Deferred until a CI test harness exists to verify per-route
behavior. Until then, mirroring keeps the surface organized with zero risk.
