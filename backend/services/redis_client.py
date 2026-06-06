"""
backend/services/redis_client.py — Shared Redis connection pool

Provides async Redis client via aioredis (redis[asyncio]).
Auto-connects on first use; degrades gracefully if Redis unavailable.
All operations are fire-and-forget (non-critical); app runs fine without it.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

try:
    import redis.asyncio as redis
    HAS_REDIS = True
except ImportError:
    redis = None
    HAS_REDIS = False

logger = logging.getLogger("entropy_prime.redis_client")

# Shared Redis connection pool (singleton)
_redis_pool: Optional[Any] = None


async def get_redis() -> Optional[Any]:
    """
    Get or create the shared Redis pool.

    Returns None if Redis is disabled or unavailable (non-blocking failure).
    """
    global _redis_pool
    
    if not HAS_REDIS or redis is None:
        logger.warning("redis[asyncio] not installed; caching disabled")
        return None
    
    if _redis_pool is not None:
        return _redis_pool
    
    redis_url = os.environ.get("EP_REDIS_URL", "")
    if not redis_url:
        logger.debug("EP_REDIS_URL not set; Redis caching disabled")
        return None
    
    try:
        _redis_pool = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            socket_keepalive=True,
            health_check_interval=30,
        )
        # Test connection
        await _redis_pool.ping()
        logger.info("[Redis] Connected to %s", redis_url)
        return _redis_pool
    except Exception as exc:
        logger.warning("[Redis] Connection failed: %s — caching disabled", exc)
        _redis_pool = None
        return None


async def close_redis() -> None:
    """Close Redis connection pool (called on app shutdown)."""
    global _redis_pool
    if _redis_pool:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("[Redis] Connection closed")


async def redis_set(key: str, value: Any, ttl_seconds: int = 3600) -> bool:
    """
    Set key=value with optional TTL. Fire-and-forget.
    
    Returns True if successful, False if Redis unavailable.
    """
    r = await get_redis()
    if not r:
        return False
    try:
        await r.setex(key, ttl_seconds, json.dumps(value) if not isinstance(value, str) else value)
        return True
    except Exception as exc:
        logger.debug("[Redis] SET failed for %s: %s", key, exc)
        return False


async def redis_get(key: str) -> Optional[str]:
    """
    Get key value. Returns None if key not found or Redis unavailable.
    
    Caller is responsible for JSON parsing if needed.
    """
    r = await get_redis()
    if not r:
        return None
    try:
        return await r.get(key)
    except Exception as exc:
        logger.debug("[Redis] GET failed for %s: %s", key, exc)
        return None


async def redis_del(key: str) -> bool:
    """Delete key. Fire-and-forget. Returns True if successful."""
    r = await get_redis()
    if not r:
        return False
    try:
        await r.delete(key)
        return True
    except Exception as exc:
        logger.debug("[Redis] DEL failed for %s: %s", key, exc)
        return False


async def redis_incr(key: str, ttl_seconds: int = 60) -> int:
    """
    Increment counter key. Auto-expire after ttl_seconds.
    
    Used for rate limiting sliding windows.
    Returns the new value, or -1 if Redis unavailable.
    """
    r = await get_redis()
    if not r:
        return -1
    try:
        # INCR + optional EXPIRE
        val = await r.incr(key)
        if val == 1:  # First increment
            await r.expire(key, ttl_seconds)
        return val
    except Exception as exc:
        logger.debug("[Redis] INCR failed for %s: %s", key, exc)
        return -1


async def redis_mget(keys: list[str]) -> dict[str, Optional[str]]:
    """
    Get multiple keys in one call.
    
    Returns dict {key: value or None}.
    """
    r = await get_redis()
    if not r:
        return {k: None for k in keys}
    try:
        values = await r.mget(keys)
        return {k: v for k, v in zip(keys, values)}
    except Exception as exc:
        logger.debug("[Redis] MGET failed: %s", exc)
        return {k: None for k in keys}
