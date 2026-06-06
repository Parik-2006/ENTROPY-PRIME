"""
backend/services/redis_client.py — Redis client factory
=========================================================

Provides a single async Redis connection pool shared across the process.
All service layers import `get_redis()` rather than constructing their own
client, so there is exactly one connection pool per worker process.

If REDIS_URL is not set the factory returns None and callers fall back to
in-process (InMemory*) implementations automatically — no code changes
needed in the services.

Usage
-----
    from backend.services.redis_client import get_redis

    async def some_service():
        r = await get_redis()
        if r is not None:
            await r.set("key", "value", ex=60)
        else:
            # fall back to in-memory store

Startup / shutdown
------------------
Call `init_redis()` in the FastAPI lifespan startup handler and
`close_redis()` in the shutdown handler so the pool is reused across
requests and cleanly flushed on exit.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("entropy_prime.redis_client")

# Module-level singleton — shared by all callers in the same process
_redis: Optional["redis.asyncio.Redis"] = None


async def init_redis() -> None:
    """
    Create the async Redis connection pool from REDIS_URL.

    Safe to call multiple times — subsequent calls are no-ops if the pool
    is already open.  Returns without error when REDIS_URL is absent so
    the app starts in in-memory mode transparently.
    """
    global _redis

    if _redis is not None:
        return  # already initialised

    url = os.environ.get("REDIS_URL", "")
    if not url:
        logger.info(
            "[Redis] REDIS_URL not set — running without Redis cache "
            "(in-memory stores will be used)"
        )
        return

    try:
        import redis.asyncio as aioredis  # type: ignore

        pool = aioredis.ConnectionPool.from_url(
            url,
            max_connections=20,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry_on_timeout=True,
        )
        client = aioredis.Redis(connection_pool=pool)
        # Verify connectivity
        await client.ping()
        _redis = client
        logger.info("[Redis] ✓ Connected to Redis")
    except Exception as exc:
        logger.warning(
            "[Redis] Could not connect (%s) — falling back to in-memory stores",
            exc,
        )
        _redis = None


async def get_redis() -> Optional["redis.asyncio.Redis"]:
    """
    Return the live Redis client, or None if Redis is unavailable.

    Callers MUST handle the None case gracefully.
    """
    return _redis


async def close_redis() -> None:
    """Close the connection pool on application shutdown."""
    global _redis
    if _redis is not None:
        try:
            await _redis.aclose()
            logger.info("[Redis] ✓ Connection pool closed")
        except Exception as exc:
            logger.warning("[Redis] Error during shutdown: %s", exc)
        finally:
            _redis = None
