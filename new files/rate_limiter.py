"""
backend/services/rate_limiter.py — Redis Sliding-Window Rate Limiter
=====================================================================

Implements a 1-minute sliding window counter using Redis atomic increments.

Keys:  ``rate_limit:{identifier}:{minute_bucket}``
TTL:   90 seconds (covers the current bucket plus a small overlap)

``identifier`` is typically the hashed API key or client IP so raw keys
are never stored in Redis.

Usage
-----
    from backend.services.rate_limiter import RateLimiter

    # In lifespan:
    rate_limiter = RateLimiter(await get_redis(), default_rpm=60)

    # In a FastAPI dependency or middleware:
    allowed, count = await rate_limiter.check("api_key_digest", limit=30)
    if not allowed:
        raise HTTPException(429, "Rate limit exceeded")

When Redis is unavailable ``check()`` always returns (True, 0) so a Redis
outage never blocks legitimate traffic — nginx rate-limiting provides the
defence-in-depth layer in that case.
"""
from __future__ import annotations

import hashlib
import logging
import math
import time
from typing import Optional, Tuple

logger = logging.getLogger("entropy_prime.rate_limiter")

_KEY_PREFIX = "rate_limit"
_BUCKET_TTL = 90   # seconds — expire each minute-bucket after 90s


def _bucket_key(identifier: str, rpm_window: int = 60) -> str:
    """
    Return the Redis key for the current time bucket.

    The identifier is hashed with SHA-256 so raw API keys / IPs are never
    stored in Redis even if someone dumps all keys.
    """
    hashed  = hashlib.sha256(identifier.encode()).hexdigest()[:16]
    bucket  = int(math.floor(time.time() / rpm_window))
    return f"{_KEY_PREFIX}:{hashed}:{bucket}"


class RateLimiter:
    """
    Async Redis-backed rate limiter.

    Parameters
    ----------
    redis_client:  aioredis.Redis or None
    default_rpm:   default requests-per-minute when not specified per-call
    """

    def __init__(self, redis_client=None, default_rpm: int = 60) -> None:
        self._r          = redis_client
        self._default_rpm = default_rpm

    async def check(
        self,
        identifier: str,
        limit: Optional[int] = None,
    ) -> Tuple[bool, int]:
        """
        Increment the counter for ``identifier`` and return (allowed, count).

        When Redis is unavailable returns (True, 0) — fail open to avoid
        locking out users during a Redis outage.

        Parameters
        ----------
        identifier: opaque string (API key digest, IP, user_id, …)
        limit:      requests-per-minute cap; defaults to self._default_rpm

        Returns
        -------
        (allowed, current_count)
        """
        if self._r is None:
            return True, 0

        cap = limit if limit is not None else self._default_rpm
        key = _bucket_key(identifier)

        try:
            pipe  = self._r.pipeline()
            pipe.incr(key)
            pipe.expire(key, _BUCKET_TTL)
            results = await pipe.execute()
            count   = int(results[0])
            allowed = count <= cap
            if not allowed:
                logger.warning(
                    "[RateLimit] EXCEEDED  key=…%s  count=%d  cap=%d",
                    key[-12:], count, cap,
                )
            return allowed, count
        except Exception as exc:
            logger.debug("[RateLimit] Redis error (fail-open): %s", exc)
            return True, 0

    async def peek(self, identifier: str) -> int:
        """Return the current request count without incrementing."""
        if self._r is None:
            return 0
        try:
            key = _bucket_key(identifier)
            raw = await self._r.get(key)
            return int(raw) if raw else 0
        except Exception:
            return 0

    async def reset(self, identifier: str) -> None:
        """Clear the rate-limit counter for an identifier (admin use)."""
        if self._r is None:
            return
        try:
            await self._r.delete(_bucket_key(identifier))
        except Exception as exc:
            logger.debug("[RateLimit] reset error: %s", exc)
