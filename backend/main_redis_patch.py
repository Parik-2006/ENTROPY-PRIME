"""
backend/main_redis_patch.py  —  Instructions for integrating Redis into main.py

This file documents the exact changes needed to main.py to enable Redis caching.
Apply these six sections in order. Each section is self-contained.

The changes are minimal and non-breaking — app runs fine without Redis
(degrades gracefully to in-memory/MongoDB).

════════════════════════════════════════════════════════════════════════════════
SECTION 1: New imports (add to top of main.py, after existing imports)
════════════════════════════════════════════════════════════════════════════════

# NEW: Redis integration
from backend.services.redis_client import get_redis, close_redis
from backend.services.session_cache import get_session_cached, invalidate_session_cache
from backend.services.rate_limiter import rate_limit_check

════════════════════════════════════════════════════════════════════════════════
SECTION 2: New singletons (add after db_handler = Database())
════════════════════════════════════════════════════════════════════════════════

# NEW: Redis client (lazy-initialized on first use)
redis_client = None


async def init_redis():
    """Initialize Redis on app startup."""
    global redis_client
    redis_client = await get_redis()
    if redis_client:
        logger.info("[Redis] Client initialized")


════════════════════════════════════════════════════════════════════════════════
SECTION 3: Update lifespan context manager (replace existing @app.on_event blocks)
════════════════════════════════════════════════════════════════════════════════

# REPLACE: existing @app.on_event("startup") and @app.on_event("shutdown")
# WITH: this single lifespan block

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("[Lifespan] Application starting...")
    await init_redis()
    yield
    # Shutdown
    logger.info("[Lifespan] Application shutting down...")
    await close_redis()

app = FastAPI(title="Entropy Prime", lifespan=lifespan)

════════════════════════════════════════════════════════════════════════════════
SECTION 4: Update _SessionGuardDep (replace existing session guard)
════════════════════════════════════════════════════════════════════════════════

# REPLACE: existing class _SessionGuardDep with this version:

class _SessionGuardDep:
    async def __call__(self, request: Request) -> dict:
        token = request.headers.get("X-Session-Token")
        if not token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing session token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # NEW: Try Redis cache first
        session = await get_session_cached(db_handler.db, token)
        
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return session

════════════════════════════════════════════════════════════════════════════════
SECTION 5: Add rate limiting to /auth/login (one-liner in handler)
════════════════════════════════════════════════════════════════════════════════

# IN: @app.post("/auth/login") handler, after getting user_email from request:

# NEW: Check rate limit (max 10 attempts per minute per email)
if not await rate_limit_check(f"login:{user_email}", max_requests=10, window_seconds=60):
    logger.warning("[Auth] Rate limit exceeded for %s", user_email)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many login attempts. Try again later."
    )

════════════════════════════════════════════════════════════════════════════════
SECTION 6: Invalidate session cache on logout (one-liner in handler)
════════════════════════════════════════════════════════════════════════════════

# IN: @app.post("/session/logout") handler, before returning response:

# NEW: Clear session cache
await invalidate_session_cache(req.session_token)

════════════════════════════════════════════════════════════════════════════════

Implementation Notes
════════════════════════════════════════════════════════════════════════════════

1. redis_client is a global variable (initialized in lifespan startup)
2. All Redis operations are async and non-blocking
3. If EP_REDIS_URL is not set, Redis is disabled (graceful degradation)
4. Session cache TTL matches session expiry time automatically
5. Rate limiter falls back to in-memory if Redis unavailable
6. No changes needed to existing business logic

Redis Key Namespaces
════════════════════════════════════════════════════════════════════════════════

session_cache:{token}
  • Sessions for logged-in users
  • TTL: matches session expiry
  
rate_limit:{key}:{bucket}
  • Login rate limiting
  • TTL: 1 minute (sliding window)

biometric:profile:{site_id}:{user_id}
  • Cached biometric profiles
  • TTL: 90 days (via biometric_profile_store.py)

governor:policy:{site_id}
  • Cached tenant policies
  • TTL: 0 (permanent; admin-managed)

honeypot:challenge:{challenge_id}
  • Honeypot challenge configs
  • TTL: 120 seconds (matches challenge expiry)

════════════════════════════════════════════════════════════════════════════════

Files Modified
════════════════════════════════════════════════════════════════════════════════

backend/main.py
  → 6 sections to apply (see above)

backend/requirements.txt
  → Added: redis[asyncio]>=5.0.0

backend/services/redis_client.py
  → New file (shared Redis pool)

backend/services/session_cache.py
  → New file (session caching wrapper)

backend/services/rate_limiter.py
  → New file (sliding-window rate limiting)

backend/services/biometric_profile_store.py
  → Already has RedisProfileStore class (compatible)

backend/services/governor_services.py
  → Already has RedisPolicyStore class (compatible)

════════════════════════════════════════════════════════════════════════════════

Testing the Integration
════════════════════════════════════════════════════════════════════════════════

1. Run MongoDB: docker-compose up mongodb
2. Run Redis: docker-compose up redis
3. Start backend:
   .env.local must have: EP_REDIS_URL=redis://localhost:6379/0
   run-backend.bat
4. Check logs for "[Redis] Connected to redis://..."
5. Call /score endpoint and verify cache hit on second call
6. Logs should show "[Redis] SET" and "[Redis] GET" for cache operations

════════════════════════════════════════════════════════════════════════════════
"""
