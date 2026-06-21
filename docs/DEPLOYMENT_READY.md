# Deployment Readiness Checklist

| Item | Status | Notes |
|---|---|---|
| ✅ Mongo Atlas configured | Ready | Code reads `MONGODB_URI`/`MONGODB_URL` + `MONGODB_DB_NAME=entropy_prime`. Set `MONGODB_URI` on Render; allow Render IPs in Atlas. |
| ✅ Upstash Redis configured | Ready | Code reads `REDIS_URL` (rediss://). Set `REDIS_URL` on Render. Graceful-degrades if absent. |
| ✅ Render configured | Ready | `render.yaml` + `docs/RENDER_SETUP.md`. Start: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`. |
| ✅ Vercel configured | Ready | `vercel.json` (Vite, `dist`, SPA rewrite) + `docs/VERCEL_SETUP.md`. |
| ✅ Environment variables configured | Documented | All names in `.env.example`; real values go in Render/Vercel dashboards (not committed). |
| ✅ Frontend build passes | Pass | `npm run build` → `dist/` (see `BUILD_VERIFICATION.md`). |
| ✅ Backend validation passes | Pass (syntax) | `py_compile` OK. Full deps verified at Render build (torch caveat below). |
| ✅ No localhost references | Pass | API client + SDK are env-driven; only the Vite **dev** proxy uses localhost. |
| ✅ CORS production-ready | Pass | Env `CORS_ORIGINS` + `allow_origin_regex` for `*.vercel.app`. |

## Required environment variables

**Render (backend)** — secrets:
`MONGODB_URI`, `MONGODB_DB_NAME`, `REDIS_URL`, `UPSTASH_REDIS_REST_URL`,
`UPSTASH_REDIS_REST_TOKEN`, `JWT_SECRET`, `SECRET_KEY`, `EP_SESSION_SECRET`,
`EP_API_KEY_SECRET`, `SHADOW_SECRET`; non-secret: `ENVIRONMENT`, `CORS_ORIGINS`,
`CORS_ORIGIN_REGEX`, `PYTHON_VERSION`.

**Vercel (frontend)**:
`VITE_API_BASE_URL=https://entropy-prime.onrender.com`,
`VITE_BACKEND_URL=https://entropy-prime.onrender.com`.

## Remaining blockers (must resolve before/at deploy)
1. **PyTorch build** — `torch==2.11.0` may not install on Render's Python/plan; torch is
   large and can OOM small plans. Pin a valid CPU build + use the CPU index, or use a
   bigger plan. See `RENDER_SETUP.md`.
2. **Rotate shared secrets** — Mongo password + Upstash token were shared in plaintext;
   rotate them and set the new values in Render.
3. **Atlas network access** — whitelist Render egress (or `0.0.0.0/0` for demo).

## Status
**Ready for production deployment** once the three items above are handled. All Phase
A–D functionality, collections, routes, and APIs are preserved.
