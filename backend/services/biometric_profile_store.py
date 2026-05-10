"""
services/biometric_profile_store.py  —  Per-(site, user) Profile Persistence

Owns all reads and writes to the profile store.  The rest of the pipeline
never touches raw storage directly.

Storage back-end
────────────────
The default implementation is an in-process dict (suitable for tests and
single-process deployments).  For production, swap in RedisProfileStore or
PostgresProfileStore below — both implement the same AbstractProfileStore
interface so callers never change.

Thread-safety
─────────────
InMemoryProfileStore uses a threading.Lock.  Redis/Postgres variants rely
on the atomicity of their own backends.
"""
from __future__ import annotations

import abc
import json
import logging
import threading
from typing import Dict, Optional

from ..pipeline.contracts import UserProfile

logger = logging.getLogger("entropy_prime.profile_store")


# ── Abstract interface ────────────────────────────────────────────────────────

class AbstractProfileStore(abc.ABC):
    """All profile stores must satisfy this interface."""

    @abc.abstractmethod
    def get(self, site_id: str, user_id: str) -> Optional[UserProfile]:
        """Return the stored profile, or None if this is the user's first visit."""

    @abc.abstractmethod
    def save(self, profile: UserProfile) -> None:
        """Persist (create or update) a profile."""

    @abc.abstractmethod
    def delete(self, site_id: str, user_id: str) -> bool:
        """Remove a profile.  Returns True if it existed."""

    # ── Convenience ──────────────────────────────────────────────────────────

    def get_or_create(self, site_id: str, user_id: str) -> tuple[UserProfile, bool]:
        """
        Return (profile, created).

        created=True  → brand-new profile, caller should persist it after
                         populating it.
        created=False → existing profile retrieved from the store.
        """
        existing = self.get(site_id, user_id)
        if existing is not None:
            return existing, False
        return UserProfile(site_id=site_id, user_id=user_id), True


# ── In-process implementation (default / testing) ─────────────────────────────

class InMemoryProfileStore(AbstractProfileStore):
    """
    Thread-safe dict-backed store.

    Suitable for:
    • unit tests (no external deps)
    • single-process deployments where cross-restart persistence isn't needed

    Keys are "{site_id}:{user_id}".
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
        logger.debug("[ProfileStore] saved %s (samples=%d)", profile.profile_key, profile.sample_count)

    def delete(self, site_id: str, user_id: str) -> bool:
        key = f"{site_id}:{user_id}"
        with self._lock:
            existed = key in self._store
            self._store.pop(key, None)
        return existed


# ── Redis-backed implementation (production) ──────────────────────────────────

class RedisProfileStore(AbstractProfileStore):
    """
    Redis-backed store.  Profiles are stored as JSON strings under the key
    ``biometric:profile:{site_id}:{user_id}``.

    Requires ``redis-py``:  pip install redis

    Usage::

        from redis import Redis
        store = RedisProfileStore(Redis.from_url("redis://localhost:6379/0"))
    """

    _KEY_PREFIX = "biometric:profile"

    def __init__(self, redis_client, ttl_seconds: int = 60 * 60 * 24 * 90) -> None:
        """
        ttl_seconds — profiles expire after this many seconds of inactivity.
                      Default: 90 days.  Each save() resets the TTL.
        """
        self._r   = redis_client
        self._ttl = ttl_seconds

    def _key(self, site_id: str, user_id: str) -> str:
        return f"{self._KEY_PREFIX}:{site_id}:{user_id}"

    def get(self, site_id: str, user_id: str) -> Optional[UserProfile]:
        raw = self._r.get(self._key(site_id, user_id))
        if raw is None:
            return None
        data = json.loads(raw)
        return UserProfile(**data)

    def save(self, profile: UserProfile) -> None:
        data = {
            "site_id":       profile.site_id,
            "user_id":       profile.user_id,
            "centroid":      profile.centroid,
            "sample_count":  profile.sample_count,
            "human_count":   profile.human_count,
            "embedding_dim": profile.embedding_dim,
        }
        self._r.setex(self._key(profile.site_id, profile.user_id), self._ttl, json.dumps(data))

    def delete(self, site_id: str, user_id: str) -> bool:
        return bool(self._r.delete(self._key(site_id, user_id)))