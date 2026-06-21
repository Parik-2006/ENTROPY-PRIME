# Render Setup (Backend — FastAPI)

Backend URL: `https://entropy-prime.onrender.com`. A `render.yaml` blueprint is
committed (secrets use `sync:false` → set them in the dashboard).

## Service configuration
| Setting | Value |
|---|---|
| Type | Web Service |
| Runtime | Python |
| Root Directory | repository root (`/`) |
| Build Command | `pip install -r backend/requirements.txt` |
| Start Command | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/health` |
| Python version | `3.11.x` (set `PYTHON_VERSION=3.11.9`) |

**Entrypoint note:** `backend/main.py:68` inserts the repo root into `sys.path`, so
`uvicorn backend.main:app` resolves all `backend.*` absolute imports correctly when run
from the repo root. Render must bind `$PORT` (handled by the start command).

## Environment variables (Render → Environment)

Secrets — paste the REAL values here (do **not** commit them):
```
MONGODB_URI               = mongodb+srv://entropy_admin:****@cluster0.skb71v7.mongodb.net/entropy_prime?retryWrites=true&w=majority&appName=Cluster0
MONGODB_DB_NAME           = entropy_prime
REDIS_URL                 = rediss://default:****@decent-shrew-132766.upstash.io:6379
UPSTASH_REDIS_REST_URL    = https://decent-shrew-132766.upstash.io
UPSTASH_REDIS_REST_TOKEN  = ****
JWT_SECRET                = <random 64-hex>
SECRET_KEY                = <random 64-hex>
EP_SESSION_SECRET         = <random 64-hex>
EP_API_KEY_SECRET         = <random 64-hex>
SHADOW_SECRET             = <random 64-hex>
```
Non-secret:
```
ENVIRONMENT       = production
CORS_ORIGINS      = http://localhost:5173,https://<your-app>.vercel.app
CORS_ORIGIN_REGEX = https://.*\.vercel\.app
```
> `****` are masked here on purpose — the real password/token were shared in chat and
> should be **rotated**. Generate secrets with: `python -c "import secrets;print(secrets.token_hex(32))"`.

## MongoDB Atlas
- Network Access → allow Render egress (or `0.0.0.0/0` for a demo).
- DB user `entropy_admin` needs `readWrite` on `entropy_prime`.
- Code reads `MONGODB_URI` (falls back to `MONGODB_URL`) + `MONGODB_DB_NAME`.

## ⚠ Build risk — PyTorch
`backend/requirements.txt` pins `torch==2.11.0`. Torch wheels are large and this exact
version may fail to install on Render's Python/plan (or OOM). If the build fails:
- pin a known CPU build and use the CPU index, e.g.
  `pip install torch==<valid-cpu-version> --extra-index-url https://download.pytorch.org/whl/cpu`
  (add the index to the build command), or
- use a larger Render plan. (Not auto-edited to avoid pinning another wrong version.)

## Verify after deploy
- `GET https://entropy-prime.onrender.com/health` → `{ "status": "ok", ... }`.
- Logs show `✓ Connected to MongoDB: entropy_prime` and `[Redis] Connected to …`.
