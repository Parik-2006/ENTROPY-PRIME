"""
backend/services/biometric_profile_store.py — Per-(site, user) Profile Persistence
====================================================================================

Three concrete implementations of the same AbstractProfileStore interface:

  InMemoryProfileStore   — dict-backed, thread-safe via threading.Lock.
                           Used for unit tests and when neither Redis nor
                           a persistent store is available.

  RedisProfileStore      — aioredis-backed.  Profiles are stored as JSON
                           strings under ``biometric:profile:{site_id}:{user_id}``.
                           TTL defaults to 90 days; each save() resets the TTL.

  get_profile_store()    — Module-level factory.  Returns a RedisProfileStore
                           when the injected redis client is non-None, otherwise
                           falls back to InMemoryProfileStore.  Call this from
                           the FastAPI lifespan after Redis has been initialised.

All behaviour and public method signatures are identical to v3.1.0; only the
Redis store gains true async support with the aioredis client.
"""
from __future__ import annotations

import abc
import json
import logging
import threading
from typing import Dict, Optional

from ..pipeline.contracts import UserProfile

logger = logging.getLogger("entropy_prime.profile_store")

# Redis key namespace
_KEY_PREFIX = "biometric:profile"
_DEFAULT_TTL = 60 * 60 * 24 * 90  # 90 days


# ── Abstract interface ────────────────────────────────────────────────────────

class AbstractProfileStore(abc.ABC):
    """Common interface for all profile store implementations."""

    @abc.abstractmethod
    def get(self, site_id: str, user_id: str) -> Optional[UserProfile]:
        """Return the stored profile, or None on first visit."""

    @abc.abstractmethod
    def save(self, profile: UserProfile) -> None:
        """Persist (create or update) a profile."""

    @abc.abstractmethod
    def delete(self, site_id: str, user_id: str) -> bool:
        """Remove a profile.  Returns True if it existed."""

    # ── Convenience ──────────────────────────────────────────────────────────

    def get_or_create(self, site_id: str, user_id: str) -> tuple[UserProfile, bool]:
        existing = self.get(site_id, user_id)
        if existing is not None:
            return existing, False
        return UserProfile(site_id=site_id, user_id=user_id), True


# ── In-process implementation ─────────────────────────────────────────────────

class InMemoryProfileStore(AbstractProfileStore):
    """
    Thread-safe dict-backed store.

    Suitable for:
    • unit tests (zero external deps)
    • single-process deployments without Redis
    • fallback when Redis is unavailable
    """

    def __init__(self) -> None:
        self._store: Dict[str, UserProfile] = {}
        self._lock  = threading.Lock()

    def get(self, site_id: str, user_id: str) -> Optional[UserProfile]:
        key = f"{site_id}:{user_id}"
        with self._lock:
            return self._store.get(key)

    def save(self, profile: UserProfile) -> None:
        with self._lock:
            self._store[profile.profile_key] = profile
        logger.debug(
            "[ProfileStore:mem] saved %s (samples=%d)",
            profile.profile_key, profile.sample_count,
        )

    def delete(self, site_id: str, user_id: str) -> bool:
        key = f"{site_id}:{user_id}"
        with self._lock:
            existed = key in self._store
            self._store.pop(key, None)
        return existed


# ── Redis-backed implementation ───────────────────────────────────────────────

class RedisProfileStore(AbstractProfileStore):
    """
    Async-capable Redis store using aioredis.

    Keys: ``biometric:profile:{site_id}:{user_id}``
    TTL:  ``ttl_seconds`` (default 90 days); reset on every save().

    The public API is intentionally synchronous to match the base class
    contract.  For truly async usage, call the async variants
    ``aget()`` / ``asave()`` / ``adelete()`` directly.
    """

    def __init__(self, redis_client, ttl_seconds: int = _DEFAULT_TTL) -> None:
        self._r   = redis_client
        self._ttl = ttl_seconds

    # ── Sync shims (blocking, for compatibility with sync callers) ─────────

    def get(self, site_id: str, user_id: str) -> Optional[UserProfile]:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Inside an async context — caller should use aget() instead
                logger.warning(
                    "[ProfileStore:redis] Sync get() called from async context; "
                    "prefer aget() for non-blocking behaviour."
                )
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(asyncio.run, self.aget(site_id, user_id))
                    return future.result(timeout=3)
            else:
                return loop.run_until_complete(self.aget(site_id, user_id))
        except Exception as exc:
            logger.error("[ProfileStore:redis] get failed: %s", exc)
            return None

    def save(self, profile: UserProfile) -> None:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # schedule as a task — fire-and-forget for sync callers
                asyncio.ensure_future(self.asave(profile))
            else:
                loop.run_until_complete(self.asave(profile))
        except Exception as exc:
            logger.error("[ProfileStore:redis] save failed: %s", exc)

    def delete(self, site_id: str, user_id: str) -> bool:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(asyncio.run, self.adelete(site_id, user_id))
                    return future.result(timeout=3)
            else:
                return loop.run_until_complete(self.adelete(site_id, user_id))
        except Exception as exc:
            logger.error("[ProfileStore:redis] delete failed: %s", exc)
            return False

    # ── True async API ────────────────────────────────────────────────────

    def _key(self, site_id: str, user_id: str) -> str:
        return f"{_KEY_PREFIX}:{site_id}:{user_id}"

    def _serialize(self, profile: UserProfile) -> str:
        return json.dumps({
            "site_id":       profile.site_id,
            "user_id":       profile.user_id,
            "centroid":      profile.centroid,
            "sample_count":  profile.sample_count,
            "human_count":   profile.human_count,
            "embedding_dim": profile.embedding_dim,
        })

    def _deserialize(self, data: str) -> Optional[UserProfile]:
        try:
            d = json.loads(data)
            p = UserProfile(site_id=d["site_id"], user_id=d["user_id"])
            p.centroid      = d.get("centroid")
            p.sample_count  = d.get("sample_count", 0)
            p.human_count   = d.get("human_count", 0)
            p.embedding_dim = d.get("embedding_dim")
            return p
        except Exception as exc:
            logger.error("[ProfileStore:redis] deserialize failed: %s", exc)
            return None

    async def aget(self, site_id: str, user_id: str) -> Optional[UserProfile]:
        try:
            raw = await self._r.get(self._key(site_id, user_id))
            if raw is None:
                return None
            return self._deserialize(raw)
        except Exception as exc:
            logger.error("[ProfileStore:redis] aget failed: %s", exc)
            return None

    async def asave(self, profile: UserProfile) -> None:
        try:
            await self._r.setex(
                self._key(profile.site_id, profile.user_id),
                self._ttl,
                self._serialize(profile),
            )
            logger.debug(
                "[ProfileStore:redis] saved %s (samples=%d)",
                profile.profile_key, profile.sample_count,
            )
        except Exception as exc:
            logger.error("[ProfileStore:redis] asave failed: %s", exc)

    async def adelete(self, site_id: str, user_id: str) -> bool:
        try:
            n = await self._r.delete(self._key(site_id, user_id))
            return bool(n)
        except Exception as exc:
            logger.error("[ProfileStore:redis] adelete failed: %s", exc)
            return False

    async def get_or_create_async(
        self, site_id: str, user_id: str
    ) -> tuple[UserProfile, bool]:
        existing = await self.aget(site_id, user_id)
        if existing is not None:
            return existing, False
        return UserProfile(site_id=site_id, user_id=user_id), True


# ── Factory ───────────────────────────────────────────────────────────────────

def get_profile_store(redis_client=None) -> AbstractProfileStore:
    """
    Return the appropriate store based on Redis availability.

    Call this once during lifespan startup after ``init_redis()`` has run:

        from backend.services.redis_client import get_redis
        from backend.services.biometric_profile_store import get_profile_store

        r = await get_redis()
        profile_store = get_profile_store(r)

    When ``redis_client`` is None the function returns an InMemoryProfileStore
    that works without any external dependencies.
    """
    if redis_client is not None:
        logger.info("[ProfileStore] Using RedisProfileStore (biometric:profile:*)")
        return RedisProfileStore(redis_client)
    logger.info("[ProfileStore] Using InMemoryProfileStore (Redis not available)")
    return InMemoryProfileStore()
