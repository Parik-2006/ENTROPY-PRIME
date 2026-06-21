"""
backend/services/rate_limiter.py — Sliding-window rate limiting via Redis

Cache key: rate_limit:{key}:{bucket}
Each bucket = 1-minute window
Sliding window = last N minutes of activity

Falls back to in-memory counter if Redis unavailable.
"""

import logging
import time
from collections import defaultdict
from typing import Optional

from backend.services.redis_client import redis_incr, redis_get

logger = logging.getLogger("entropy_prime.rate_limiter")

# In-memory fallback counters (when Redis unavailable)
_in_memory_counters: dict[str, list[float]] = defaultdict(list)


async def rate_limit_check(
    key: str,
    max_requests: int,
    window_seconds: int = 60,
) -> bool:
    """
    Check if key has exceeded rate limit.
    
    Returns True if under limit, False if exceeded.
    
    Sliding window: tracks request timestamps in last window_seconds.
    Uses Redis if available, falls back to in-memory.
    """
    bucket_key = f"rate_limit:{key}:{int(time.time() // 60)}"
    
    # Try Redis
    val = await redis_incr(bucket_key, ttl_seconds=window_seconds)
    if val >= 0:
        return val <= max_requests
    
    # Fallback to in-memory
    now = time.time()
    cutoff = now - window_seconds
    
    # Prune old timestamps
    if key in _in_memory_counters:
        _in_memory_counters[key] = [
            ts for ts in _in_memory_counters[key] if ts > cutoff
        ]
    
    # Check limit
    if len(_in_memory_counters[key]) >= max_requests:
        logger.debug("[RateLimit] %s exceeded (in-memory fallback)", key)
        return False
    
    # Record this request
    _in_memory_counters[key].append(now)
    return True


async def rate_limit_reset(key: str) -> None:
    """Clear rate limit for key (e.g., on successful auth)."""
    _in_memory_counters.pop(key, None)
    logger.debug("[RateLimit] Reset for %s", key)
