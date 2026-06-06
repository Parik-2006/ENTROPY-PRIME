"""
backend/services/session_cache.py — Redis Session Cache
=========================================================

Thin caching layer that sits in front of the MongoDB ``get_session()`` call.

Keys:  ``session_cache:{session_token}``
TTL:   5 minutes (refreshed on every cache hit)
Value: JSON-serialised session document (ObjectIds already stringified)

When Redis is unavailable every call falls through to MongoDB transparently.
The cache is write-through: ``set()`` writes to Redis and the caller is
responsible for writing to MongoDB (the existing database.py functions
handle persistence).  On ``invalidate()`` the Redis key is deleted
immediately so subsequent requests are forced to re-query MongoDB.

Usage in main.py (inside require_active_session and session_verify)
--------------------------------------------------------------------
    from backend.services.session_cache import SessionCache

    # In lifespan:
    session_cache = SessionCache(await get_redis())

    # In get_session fast-path:
    session = await session_cache.get(token)
    if session is None:
        session = await db_database.get_session(db, token)
        if session:
            await session_cache.set(token, session)

    # On logout / force-logout:
    await session_cache.invalidate(token)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("entropy_prime.session_cache")

_KEY_PREFIX = "session_cache"
_TTL        = 300   # 5 minutes — short enough to not stale, long enough to matter


def _make_key(token: str) -> str:
    return f"{_KEY_PREFIX}:{token}"


def _serialize(session: dict) -> str:
    """JSON-safe serialisation — converts datetime objects to ISO strings."""
    def _default(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    return json.dumps(session, default=_default)


def _deserialize(raw: str) -> Optional[dict]:
    try:
        return json.loads(raw)
    except Exception as exc:
        logger.warning("[SessionCache] deserialize failed: %s", exc)
        return None


class SessionCache:
    """
    Redis-backed session document cache.

    All methods are async and swallow Redis errors so a Redis outage
    never breaks authentication — it just adds a MongoDB round-trip.
    """

    def __init__(self, redis_client=None) -> None:
        self._r = redis_client

    # ── Public API ────────────────────────────────────────────────────────────

    async def get(self, token: str) -> Optional[dict]:
        """Return cached session document, or None on miss / Redis down."""
        if self._r is None:
            return None
        try:
            raw = await self._r.get(_make_key(token))
            if raw is None:
                return None
            # Refresh TTL on hit — active sessions stay warm
            await self._r.expire(_make_key(token), _TTL)
            return _deserialize(raw)
        except Exception as exc:
            logger.debug("[SessionCache] get error (non-critical): %s", exc)
            return None

    async def set(self, token: str, session: dict) -> None:
        """Write a session document into the cache."""
        if self._r is None:
            return
        try:
            await self._r.setex(_make_key(token), _TTL, _serialize(session))
        except Exception as exc:
            logger.debug("[SessionCache] set error (non-critical): %s", exc)

    async def invalidate(self, token: str) -> None:
        """Remove a session from the cache immediately (logout / force-logout)."""
        if self._r is None:
            return
        try:
            await self._r.delete(_make_key(token))
            logger.debug("[SessionCache] invalidated token …%s", token[-8:])
        except Exception as exc:
            logger.debug("[SessionCache] invalidate error (non-critical): %s", exc)

    async def update_trust(self, token: str, trust_score: float) -> None:
        """
        Patch the trust_score field on a cached session document in-place.

        Called after every /session/verify heartbeat so the cache stays in
        sync without a full evict-and-reload cycle.
        """
        if self._r is None:
            return
        try:
            raw = await self._r.get(_make_key(token))
            if raw is None:
                return
            session = _deserialize(raw)
            if session is None:
                return
            session["trust_score"] = round(float(trust_score), 4)
            await self._r.setex(_make_key(token), _TTL, _serialize(session))
        except Exception as exc:
            logger.debug("[SessionCache] update_trust error (non-critical): %s", exc)
