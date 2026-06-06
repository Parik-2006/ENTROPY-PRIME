"""
backend/main_redis_patch.py
============================
This file documents the MINIMAL changes required to wire Redis into the
existing main.py.  It is NOT a full replacement of main.py — apply the
diff sections marked with ── ADD ── / ── REPLACE ── below.

After applying:
  • Redis is initialised on startup and closed on shutdown.
  • Biometric profile store and governor service use Redis when available.
  • Session lookups go through the Redis cache before hitting MongoDB.
  • Session invalidation (logout / force-logout) purges the Redis cache entry.
  • A RateLimiter instance is available for optional per-route enforcement.

Search for each "── SECTION N ──" block in main.py and apply the change.
"""

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — New imports  (add after existing service imports, ~line 30)
# ══════════════════════════════════════════════════════════════════════════════

from backend.services.redis_client import init_redis, get_redis, close_redis
from backend.services.session_cache import SessionCache
from backend.services.rate_limiter import RateLimiter
from backend.services.governor_services import (
    get_governor_service,
    HoneypotChallengeStore,
)
from backend.services.biometric_profile_store import get_profile_store


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Module-level singletons  (add after existing singletons, ~line 60)
# ══════════════════════════════════════════════════════════════════════════════

# These are set during lifespan startup.
session_cache:     "SessionCache | None"     = None
rate_limiter:      "RateLimiter | None"      = None
challenge_store:   "HoneypotChallengeStore | None" = None
profile_store:     "object | None"           = None   # AbstractProfileStore
governor_service:  "object | None"           = None   # GovernorService


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Lifespan  (replace the existing lifespan function)
# ══════════════════════════════════════════════════════════════════════════════

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    global orchestrator, watchdog_service
    global session_cache, rate_limiter, challenge_store, profile_store, governor_service

    logger.info("🚀 Entropy Prime v3.2 starting up…")

    # ── 1. MongoDB ─────────────────────────────────────────────────────────────
    await db_handler.connect_to_mongo()
    attach_db(db_handler.db)
    load_jwt_public_key()
    _load_checkpoints()

    # ── 2. Redis (optional — graceful degradation if unavailable) ─────────────
    await init_redis()
    redis = await get_redis()

    # ── 3. Redis-backed service layer ─────────────────────────────────────────
    session_cache   = SessionCache(redis)
    rate_limiter    = RateLimiter(redis, default_rpm=60)
    challenge_store = HoneypotChallengeStore(redis)
    profile_store   = get_profile_store(redis)
    governor_service = get_governor_service(
        dqn_agent=dqn_agent,
        ppo_agent=ppo_agent,
        redis_client=redis,
    )

    # ── 4. Watchdog service ────────────────────────────────────────────────────
    watchdog_service = WatchdogService(db_handler)

    # ── 5. Auto-seed test data in development ──────────────────────────────────
    if os.environ.get("ENVIRONMENT") == "development":
        from database import create_tenant, create_site
        import hmac as _hmac, hashlib
        try:
            if not await db_handler.db.tenants.find_one({"admin_email": "admin@test.com"}):
                tenant_id = await create_tenant(db_handler.db, "Test Corp", "admin@test.com", "pro")
                raw_api_key    = "test-sdk-key-123"
                api_key_secret = os.environ.get("EP_API_KEY_SECRET", "")
                key_digest     = _hmac.new(
                    api_key_secret.encode(), raw_api_key.encode(), hashlib.sha256
                ).hexdigest()
                await create_site(db_handler.db, tenant_id, "Test Site", "localhost", key_digest)
                logger.info("🌱 Database seeded with test tenant and site")
        except Exception as exc:
            logger.warning("Seeding failed: %s", exc)

    # ── 6. Pipeline orchestrator ───────────────────────────────────────────────
    orchestrator = PipelineOrchestrator(
        dqn_agent      = dqn_agent,
        mab_agent      = mab_agent,
        gov_ppo_agent  = gov_ppo_agent,
        ppo_agent      = ppo_agent,
        shadow_secret  = SHADOW_SECRET,
        session_secret = SESSION_SECRET,
    )

    # ── 7. Background TTL sweep ────────────────────────────────────────────────
    import asyncio
    async def _threat_ttl_sweep():
        while True:
            try:
                await asyncio.sleep(6 * 60 * 60)
                if watchdog_service:
                    count = await watchdog_service.expire_stale_threats()
                    logger.info("[TTL Sweep] Expired %d stale threat records", count)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[TTL Sweep] Failed: %s", exc)

    sweep_task = asyncio.create_task(_threat_ttl_sweep())
    logger.info("✓ Entropy Prime v3.2 initialised — 4-stage pipeline + Redis cache active")
    yield

    # ── Shutdown ───────────────────────────────────────────────────────────────
    logger.info("🛑 Entropy Prime shutting down…")
    sweep_task.cancel()
    try:
        await sweep_task
    except Exception:
        pass
    await close_redis()
    try:
        await db_handler.close_mongo_connection()
        logger.info("✓ MongoDB connection closed")
    except Exception as exc:
        logger.error("Error during DB shutdown: %s", exc)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Session guard with cache  (replace _SessionGuardDep.__call__)
# ══════════════════════════════════════════════════════════════════════════════

class _SessionGuardDep:
    """
    Session validation with Redis cache front-end.

    Lookup order:
      1. Redis cache  (fast path, ~1ms)
      2. MongoDB      (authoritative, ~5-10ms)

    A cache miss or Redis unavailability falls through silently.
    """

    async def __call__(self, request) -> dict:
        token = request.headers.get("X-Session-Token")
        if not token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.removeprefix("Bearer ").strip()

        if not token:
            raise HTTPException(
                status_code=401,
                detail="Missing session token (expected X-Session-Token or Authorization: Bearer)",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # ── Fast path: Redis cache ─────────────────────────────────────────
        if session_cache is not None:
            cached = await session_cache.get(token)
            if cached is not None:
                return cached

        # ── Slow path: MongoDB ────────────────────────────────────────────
        try:
            session = await get_session(db_handler.db, token)
        except Exception as exc:
            logger.error("[SessionGuard] DB error: %s", exc)
            raise HTTPException(status_code=503, detail="Session store unavailable")

        if session is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired session",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Populate cache for subsequent requests
        if session_cache is not None:
            await session_cache.set(token, session)

        return session


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Invalidate cache on logout  (update /auth/logout handler)
# ══════════════════════════════════════════════════════════════════════════════

# In the logout() route handler, add this line after invalidate_session():
#
#     if session_cache is not None:
#         await session_cache.invalidate(token)
#
# Example (replace existing try block in logout()):

async def logout_with_cache(req=None, session_token=None):
    """Updated logout handler — invalidates MongoDB session AND Redis cache."""
    token = session_token
    if not token and req:
        token = req.session_token
    if not token:
        raise HTTPException(status_code=422, detail="session_token required")
    try:
        await invalidate_session(db_handler.db, token)
        # ── ADD: purge from Redis cache ──
        if session_cache is not None:
            await session_cache.invalidate(token)
        return {"success": True, "message": "Logged out successfully"}
    except Exception as exc:
        logger.error("[Auth] Logout error: %s", exc)
        raise HTTPException(status_code=500, detail="Logout failed")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Cache trust-score update after heartbeat  (in session_verify)
# ══════════════════════════════════════════════════════════════════════════════

# After the existing `await update_session_trust_score(...)` call, add:
#
#     if session_cache is not None:
#         await session_cache.update_trust(req.session_token, wd.trust_score)
#
# And on FORCE_LOGOUT, also invalidate:
#
#     if session_cache is not None:
#         await session_cache.invalidate(req.session_token)
