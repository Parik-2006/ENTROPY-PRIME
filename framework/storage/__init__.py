"""
framework.storage — Persistence Layer
=====================================

All durable state lives here: MongoDB (users, sessions, biometric_profiles,
honeypot, threat_intelligence, drift_events, tenants, sites) and Redis
(session cache, rate-limit counters).

A later phase will split ``backend/database.py`` into per-collection
repositories under ``framework/storage/mongo/`` and move the Redis helpers
under ``framework/storage/redis/``. For now this module re-exports the existing
data-access layer unchanged.

Facade mapping (v0.1 — re-export, no code moved)
------------------------------------------------
    .mongo        <- backend.database            (Database class + free functions)
    .Database     <- backend.database.Database
    .redis_client <- backend.services.redis_client
    .session_cache<- backend.services.session_cache
    .rate_limiter <- backend.services.rate_limiter

Onboarding-state constants are also re-exported for convenience.
"""
from __future__ import annotations

# ── MongoDB data-access layer (motor) ────────────────────────────────────────
try:
    from backend import database as mongo
    from backend.database import (
        Database,
        # onboarding constants
        ONBOARDING_COLLECTING,
        ONBOARDING_SYNCING,
        ONBOARDING_STABLE,
        ONBOARDING_DRIFTED,
        STABLE_SAMPLE_THRESHOLD,
    )
    MONGO_AVAILABLE = True
except Exception as exc:  # pragma: no cover - motor may be absent
    mongo = None
    Database = None
    ONBOARDING_COLLECTING = "collecting"
    ONBOARDING_SYNCING = "syncing"
    ONBOARDING_STABLE = "stable"
    ONBOARDING_DRIFTED = "drifted"
    STABLE_SAMPLE_THRESHOLD = 50
    MONGO_AVAILABLE = False
    _MONGO_ERROR = str(exc)

# ── Redis helpers (redis.asyncio) ────────────────────────────────────────────
try:
    from backend.services import redis_client
    from backend.services import session_cache
    from backend.services import rate_limiter
    REDIS_AVAILABLE = True
except Exception as exc:  # pragma: no cover - redis may be absent
    redis_client = None
    session_cache = None
    rate_limiter = None
    REDIS_AVAILABLE = False
    _REDIS_ERROR = str(exc)

__all__ = [
    "mongo",
    "Database",
    "MONGO_AVAILABLE",
    "redis_client",
    "session_cache",
    "rate_limiter",
    "REDIS_AVAILABLE",
    "ONBOARDING_COLLECTING",
    "ONBOARDING_SYNCING",
    "ONBOARDING_STABLE",
    "ONBOARDING_DRIFTED",
    "STABLE_SAMPLE_THRESHOLD",
]
