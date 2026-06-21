"""
backend/services/session_cache.py — Redis-backed session caching

Wraps session storage with a Redis L1 cache.
Cache key: session_cache:{token}
Cache TTL: matches session expiry

Falls back to MongoDB if Redis unavailable.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from backend.database import get_session as db_get_session
from backend.services.redis_client import redis_get, redis_set, redis_del

logger = logging.getLogger("entropy_prime.session_cache")


async def get_session_cached(db, token: str) -> Optional[dict]:
    """
    Get session, checking Redis cache first.
    
    Cache hit → return immediately
    Cache miss → fetch from MongoDB, populate cache, return
    """
    cache_key = f"session_cache:{token}"
    
    # Try Redis
    cached = await redis_get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            logger.debug("[SessionCache] Cache corrupted for %s", token[:16])
            await redis_del(cache_key)
    
    # Fallback to MongoDB
    session = await db_get_session(db, token)
    if session:
        # Cache for remaining TTL
        expires_at = session.get("expires_at")
        if expires_at and isinstance(expires_at, datetime):
            ttl = int((expires_at - datetime.utcnow()).total_seconds())
            if ttl > 0:
                await redis_set(
                    cache_key,
                    json.dumps(session, default=str),
                    ttl_seconds=ttl
                )
        return session
    
    return None


async def invalidate_session_cache(token: str) -> None:
    """Remove session from cache (called on logout)."""
    cache_key = f"session_cache:{token}"
    await redis_del(cache_key)
