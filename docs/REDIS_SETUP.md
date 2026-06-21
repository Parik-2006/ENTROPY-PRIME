# Redis Setup (Upstash)

## How the app uses Redis
- Client: `backend/services/redis_client.py` (async `redis.asyncio`). It is a
  **non-critical cache** — the app degrades gracefully if Redis is unavailable
  (session cache falls back to DB; rate limiting allows). No functionality is lost.
- Consumers: `services/session_cache.py`, `services/rate_limiter.py`.

## Which variable the app reads
`get_redis()` now resolves the connection URL in this order (FIXED this phase):
```
EP_REDIS_URL  →  REDIS_URL  →  REDIS_URI
```
For Upstash, set **`REDIS_URL`** to the TLS protocol URL (redis-py speaks the Redis
wire protocol over `rediss://`):
```
REDIS_URL = rediss://default:****@decent-shrew-132766.upstash.io:6379
```

## Upstash REST credentials
```
UPSTASH_REDIS_REST_URL   = https://decent-shrew-132766.upstash.io
UPSTASH_REDIS_REST_TOKEN = ****
```
These are for Upstash's **HTTP REST** API. The current code uses the native Redis
protocol (`REDIS_URL`), so the REST pair is **not required** for the app to work — it
is documented for reference / future REST-based usage. Keep them set on Render in case a
future component uses REST; they are listed in `.env.example` and `render.yaml`.

> `****` masked — rotate the token; it was shared in chat.

## Verify
- Render logs: `[Redis] Connected to rediss://…` on startup.
- If you only set the REST pair and not `REDIS_URL`, the log will say
  *"No Redis URL set … caching disabled"* — set `REDIS_URL` to enable caching.
- Functional check: rate-limited endpoints and session-cache paths still work either way
  (graceful degradation).
