"""
backend/database.py  —  Unified Data-Access Layer (MongoDB / Motor)

v4.0.0 — full merge of threat intelligence into the existing Motor stack.

Changes from v3.1.0
───────────────────
• Added ThreatRecord dataclass and all threat-intelligence operations
  (upsert_threat, get_active_threats, get_active_threats_by_ip,
   expire_threats_before, broadcast_global_threat) — all backed by the
  existing MongoDB connection rather than a separate SQL engine.
• Added a `threat_broadcasts` collection for at-least-once delivery logging.
• _create_indexes now covers both new collections.
• No existing behaviour changed; all v3.1.0 public functions are intact
  and signature-compatible.

MongoDB collections introduced
───────────────────────────────
  threat_intelligence  — one document per (fingerprint_hash, tenant_id, action)
                         triple; weight is accumulated via $inc on upsert.

    {
      fingerprint_hash : str,          # SHA-256 hex of raw fingerprint
      ip_address       : str | None,
      tenant_id        : str,
      action           : str,          # WatchdogAction.value
      weight           : float,        # accumulated via $inc
      e_rec            : float,
      trust_score      : float,
      reason           : str | None,
      ts               : float,        # Unix epoch of most-recent observation
      expired_at       : float | None  # None = active; set by TTL sweep
    }

  threat_broadcasts  — append-only delivery log for global notifications.

    {
      fingerprint_hash : str,
      ip_address       : str | None,
      cumulative_score : float,
      tenant_count     : int,
      action           : str,
      payload          : dict,         # full broadcast payload
      sent_at          : float,
      delivered        : bool
    }
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

logger = logging.getLogger("entropy_prime.database")


# ─────────────────────────────────────────────────────────────────────────────
# DTOs
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ThreatRecord:
    """
    One per-tenant observation of a suspicious fingerprint.
    Mirrors the document shape in the `threat_intelligence` collection.
    """
    fingerprint_hash: str
    tenant_id:        str
    action:           str
    weight:           float
    e_rec:            float
    trust_score:      float
    ts:               float
    ip_address:       Optional[str]   = None
    reason:           Optional[str]   = None
    expired_at:       Optional[float] = None


# ─────────────────────────────────────────────────────────────────────────────
# Database connection class
# ─────────────────────────────────────────────────────────────────────────────

class Database:
    """
    Motor-backed async data-access layer.

    Instantiate once at application startup and share via FastAPI dependency::

        _db_instance: Database | None = None

        def get_db() -> Database:
            assert _db_instance is not None, "Database not initialised"
            return _db_instance

        @app.on_event("startup")
        async def startup():
            global _db_instance
            _db_instance = Database()
            await _db_instance.connect_to_mongo()

    All threat-intelligence operations are instance methods on this class.
    All pre-existing operations remain free functions that accept an
    AsyncIOMotorDatabase handle (unchanged from v3.1.0).
    """

    def __init__(self) -> None:
        self.client:      Optional[AsyncIOMotorClient]   = None
        self.db:          Optional[AsyncIOMotorDatabase] = None
        self.max_retries: int   = 5
        self.retry_delay: float = 2.0

    # ── Connection lifecycle ──────────────────────────────────────────────────

    async def connect_to_mongo(self) -> None:
        """Connect to MongoDB with retry logic. Falls back to mongomock for dev."""
        mongo_url = os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
        db_name   = os.environ.get("MONGODB_DB_NAME", "entropy_prime")

        for attempt in range(1, self.max_retries + 1):
            try:
                self.client = AsyncIOMotorClient(
                    mongo_url,
                    serverSelectionTimeoutMS=5000,
                    socketTimeoutMS=5000,
                    retryWrites=True,
                    maxPoolSize=50,
                    minPoolSize=10,
                )
                await self.client.admin.command("ping")
                self.db = self.client[db_name]
                await self._create_indexes()
                logger.info("✓ Connected to MongoDB: %s", db_name)
                return
            except (ServerSelectionTimeoutError, ConnectionFailure) as exc:
                logger.warning(
                    "Connection attempt %d/%d failed: %s",
                    attempt, self.max_retries, exc,
                )
                if attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.warning(
                        "Failed to connect to real MongoDB after %d attempts",
                        self.max_retries,
                    )
                    logger.info("Falling back to mongomock (in-memory) for development…")
                    try:
                        from mongomock_motor import AsyncMongoMockClient as MockClient
                        self.client = MockClient()
                        self.db     = self.client[db_name]
                        logger.info(
                            "✓ Using mongomock_motor database: %s (dev/test mode)", db_name
                        )
                        return
                    except Exception as mock_exc:
                        logger.error("Failed to initialise mongomock: %s", mock_exc)
                        raise

    async def close_mongo_connection(self) -> None:
        if self.client:
            self.client.close()
            logger.info("✓ MongoDB connection closed")

    async def _create_indexes(self) -> None:
        """Create all collection indexes. Safe to call on every startup (idempotent)."""
        try:
            # ── Pre-existing collections ──────────────────────────────────────
            await self.db.tenants.create_index("admin_email", unique=True)
            await self.db.sites.create_index("key_digest", unique=True)
            await self.db.sites.create_index("tenant_id")
            await self.db.users.create_index("email", unique=True)
            await self.db.users.create_index("tenant_id")
            await self.db.sessions.create_index("tenant_id")
            await self.db.sessions.create_index("site_id")
            await self.db.biometric_profiles.create_index("tenant_id")
            await self.db.biometric_profiles.create_index("site_id")

            # ── threat_intelligence ───────────────────────────────────────────
            # Compound unique key: one document per (fp, tenant, action) triple.
            # This makes $inc weight accumulation safe under concurrent upserts.
            await self.db.threat_intelligence.create_index(
                [
                    ("fingerprint_hash", ASCENDING),
                    ("tenant_id",        ASCENDING),
                    ("action",           ASCENDING),
                ],
                unique=True,
                name="idx_ti_fp_tenant_action",
            )
            # Fast read path for is_globally_flagged() lookups
            await self.db.threat_intelligence.create_index(
                [("fingerprint_hash", ASCENDING), ("expired_at", ASCENDING)],
                name="idx_ti_fp_hash",
            )
            # Fast read path for IP-level lookups
            await self.db.threat_intelligence.create_index(
                [("ip_address", ASCENDING), ("expired_at", ASCENDING)],
                name="idx_ti_ip",
            )
            # TTL sweep efficiency
            await self.db.threat_intelligence.create_index(
                [("ts", ASCENDING)],
                name="idx_ti_ts",
            )

            # ── threat_broadcasts ─────────────────────────────────────────────
            await self.db.threat_broadcasts.create_index(
                [("fingerprint_hash", ASCENDING)],
                name="idx_tb_fp",
            )
            # Retry sweeper queries {delivered: false} ordered by sent_at
            await self.db.threat_broadcasts.create_index(
                [("delivered", ASCENDING), ("sent_at", ASCENDING)],
                name="idx_tb_delivered",
            )

            logger.info("✓ All database indexes created")
        except Exception as exc:
            logger.error("Index creation error: %s", exc, exc_info=True)
            raise

    # ── Threat intelligence — write path ──────────────────────────────────────

    async def upsert_threat(self, record: ThreatRecord) -> None:
        """
        Insert a new threat observation or *accumulate* weight if a document
        already exists for the same (fingerprint_hash, tenant_id, action) triple.

        Using $inc for weight means concurrent upserts from multiple app
        instances are safe with no application-level locking.

        `expired_at` is explicitly reset to None so a previously TTL-expired
        record becomes active again on a fresh observation — identical
        semantics to the SQL `ON CONFLICT ... expired_at = NULL` behaviour.

        IP address follows a "first wins, update on new value" strategy:
        $setOnInsert keeps the original IP; the conditional $set in the
        update path replaces it only when a non-None IP is provided, mirroring
        SQL's COALESCE(EXCLUDED.ip_address, existing.ip_address).
        """
        filter_doc = {
            "fingerprint_hash": record.fingerprint_hash,
            "tenant_id":        record.tenant_id,
            "action":           record.action,
        }
        set_fields: dict = {
            "e_rec":       record.e_rec,
            "trust_score": record.trust_score,
            "reason":      record.reason,
            "ts":          record.ts,
            "expired_at":  None,
        }
        if record.ip_address:
            # Overwrite IP only when a fresh value is supplied
            set_fields["ip_address"] = record.ip_address

        update_doc = {
            "$inc": {"weight": record.weight},
            "$set": set_fields,
            "$setOnInsert": {
                # Written exactly once, on document creation
                "fingerprint_hash": record.fingerprint_hash,
                "tenant_id":        record.tenant_id,
                "action":           record.action,
                "ip_address":       record.ip_address,
                "created_at":       datetime.utcnow(),
            },
        }
        await self.db.threat_intelligence.update_one(
            filter_doc, update_doc, upsert=True
        )
        logger.debug(
            "[DB.TI] upsert fp=%.8s tenant=%s action=%s weight+=%.1f",
            record.fingerprint_hash, record.tenant_id,
            record.action, record.weight,
        )

    # ── Threat intelligence — read paths ──────────────────────────────────────

    async def get_active_threats(
        self, fingerprint_hash: str, since: float
    ) -> list[ThreatRecord]:
        """
        Return all non-expired threat documents for a fingerprint hash whose
        most-recent observation timestamp is >= `since` (Unix epoch float).
        """
        cursor = self.db.threat_intelligence.find(
            {
                "fingerprint_hash": fingerprint_hash,
                "ts":               {"$gte": since},
                "expired_at":       None,
            }
        ).sort("ts", DESCENDING)
        return [_doc_to_threat(doc) async for doc in cursor]

    async def get_active_threats_by_ip(
        self, ip_address: str, since: float
    ) -> list[ThreatRecord]:
        """
        Return all non-expired threat documents associated with an IP address
        whose most-recent observation timestamp is >= `since`.
        """
        cursor = self.db.threat_intelligence.find(
            {
                "ip_address": ip_address,
                "ts":         {"$gte": since},
                "expired_at": None,
            }
        ).sort("ts", DESCENDING)
        return [_doc_to_threat(doc) async for doc in cursor]

    # ── Threat intelligence — TTL sweep ───────────────────────────────────────

    async def expire_threats_before(self, cutoff: float) -> int:
        """
        Soft-delete all active threat documents older than `cutoff` epoch by
        setting `expired_at` to the current Unix timestamp.  Documents are
        retained for forensic audit; they are simply excluded from scoring
        queries.

        Returns the number of documents updated.  Call from a periodic
        background task (e.g. APScheduler, Celery beat).
        """
        result = await self.db.threat_intelligence.update_many(
            {
                "ts":         {"$lt": cutoff},
                "expired_at": None,
            },
            {"$set": {"expired_at": time.time()}},
        )
        logger.info(
            "[DB.TI] Expired %d stale threat records (cutoff=%.0f)",
            result.modified_count, cutoff,
        )
        return result.modified_count

    # ── Threat intelligence — broadcast ───────────────────────────────────────

    async def broadcast_global_threat(self, payload) -> None:
        """
        Persist a broadcast record for at-least-once delivery, then call
        `_deliver_broadcast` to fan-out to the configured notification channel.

        Persistence happens BEFORE the network call so a crashed delivery can
        be retried by a background sweeper that queries `{delivered: false}`.
        The `delivered` flag is set to True only after a successful delivery.
        """
        payload_dict = {
            "fingerprint_hash": payload.fingerprint_hash,
            "ip_address":       payload.ip_address,
            "cumulative_score": payload.cumulative_score,
            "tenant_count":     payload.tenant_count,
            "action":           payload.action,
            "timestamp":        payload.timestamp,
        }
        broadcast_doc = {
            "fingerprint_hash": payload.fingerprint_hash,
            "ip_address":       payload.ip_address,
            "cumulative_score": payload.cumulative_score,
            "tenant_count":     payload.tenant_count,
            "action":           payload.action,
            "payload":          payload_dict,
            "sent_at":          payload.timestamp,
            "delivered":        False,
        }
        result = await self.db.threat_broadcasts.insert_one(broadcast_doc)
        inserted_id = result.inserted_id

        # Best-effort delivery; never propagates exception to caller
        try:
            await self._deliver_broadcast(payload_dict)
            await self.db.threat_broadcasts.update_one(
                {"_id": inserted_id},
                {"$set": {"delivered": True}},
            )
        except Exception as exc:
            logger.error(
                "[DB.TI] Broadcast delivery failed (will retry on sweep): %s", exc
            )

    async def _deliver_broadcast(self, payload: dict) -> None:
        """
        Override this method to fan-out to webhooks, SNS, Redis pub/sub,
        WebSocket hub, etc.

        The default implementation logs at WARNING level — sufficient for
        local dev and unit tests with no external dependencies.
        """
        logger.warning(
            "[DB.TI] GLOBAL THREAT BROADCAST (no delivery backend configured): %s",
            json.dumps(payload, default=str),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Private helper
# ─────────────────────────────────────────────────────────────────────────────

def _doc_to_threat(doc: dict) -> ThreatRecord:
    """Convert a raw MongoDB document to a ThreatRecord dataclass."""
    return ThreatRecord(
        fingerprint_hash = doc["fingerprint_hash"],
        tenant_id        = doc["tenant_id"],
        action           = doc["action"],
        weight           = doc.get("weight",      0.0),
        e_rec            = doc.get("e_rec",        0.0),
        trust_score      = doc.get("trust_score",  1.0),
        ts               = doc.get("ts",           0.0),
        ip_address       = doc.get("ip_address"),
        reason           = doc.get("reason"),
        expired_at       = doc.get("expired_at"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tenant & Site Operations  (unchanged from v3.1.0)
# ─────────────────────────────────────────────────────────────────────────────

async def create_tenant(
    db: AsyncIOMotorDatabase, name: str, admin_email: str, tier: str = "free"
) -> str:
    tenant_doc = {
        "name":              name,
        "admin_email":       admin_email.lower(),
        "subscription_tier": tier,
        "created_at":        datetime.utcnow(),
        "is_active":         True,
    }
    result = await db.tenants.insert_one(tenant_doc)
    return str(result.inserted_id)


async def get_tenant_by_id(
    db: AsyncIOMotorDatabase, tenant_id: str
) -> Optional[dict]:
    try:
        tenant = await db.tenants.find_one({"_id": ObjectId(tenant_id)})
        if tenant:
            tenant["_id"] = str(tenant["_id"])
        return tenant
    except Exception:
        return None


async def create_site(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    name: str,
    domain: str,
    key_digest: str,
) -> str:
    site_doc = {
        "tenant_id":  tenant_id,
        "site_name":  name,
        "domain":     domain.lower(),
        "key_digest": key_digest,
        "created_at": datetime.utcnow(),
        "is_active":  True,
    }
    result = await db.sites.insert_one(site_doc)
    return str(result.inserted_id)


async def get_site_by_api_key(
    db: AsyncIOMotorDatabase, key_digest: str
) -> Optional[dict]:
    site = await db.sites.find_one({"key_digest": key_digest, "is_active": True})
    if site:
        site["_id"] = str(site["_id"])
    return site


# ─────────────────────────────────────────────────────────────────────────────
# User Operations  (unchanged from v3.1.0)
# ─────────────────────────────────────────────────────────────────────────────

async def user_exists(
    db: AsyncIOMotorDatabase,
    email: str,
    tenant_id: Optional[str] = None,
) -> bool:
    query = {"email": email.lower()}
    if tenant_id:
        query["tenant_id"] = tenant_id
    return await db.users.find_one(query) is not None


async def create_user(
    db: AsyncIOMotorDatabase,
    email: str,
    password_hash: str,
    tenant_id: Optional[str] = None,
) -> str:
    user_doc = {
        "tenant_id":         tenant_id,
        "email":             email.lower(),
        "password_hash":     password_hash,
        "created_at":        datetime.utcnow(),
        "updated_at":        datetime.utcnow(),
        "last_login":        None,
        "is_active":         True,
        "security_level":    "standard",
        "biometric_profile": {},
    }
    result = await db.users.insert_one(user_doc)
    return str(result.inserted_id)


async def get_user_by_email(
    db: AsyncIOMotorDatabase, email: str
) -> Optional[dict]:
    user = await db.users.find_one({"email": email.lower()})
    if user:
        user["_id"] = str(user["_id"])
    return user


async def get_user_by_id(
    db: AsyncIOMotorDatabase, user_id: str
) -> Optional[dict]:
    try:
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if user:
            user["_id"] = str(user["_id"])
        return user
    except Exception:
        return None


async def update_last_login(
    db: AsyncIOMotorDatabase, user_id: str
) -> None:
    try:
        await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"last_login": datetime.utcnow()}},
        )
    except Exception:
        pass


async def update_user_security_level(
    db: AsyncIOMotorDatabase, user_id: str, level: str
) -> None:
    try:
        await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"security_level": level, "updated_at": datetime.utcnow()}},
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Session Operations  (unchanged from v3.1.0)
# ─────────────────────────────────────────────────────────────────────────────

async def create_session(
    db: AsyncIOMotorDatabase,
    user_id: str,
    session_token: str,
    latent_vector: list,
    tenant_id: Optional[str] = None,
    site_id:   Optional[str] = None,
    expires_in_minutes: int  = 30,
) -> str:
    session_doc = {
        "tenant_id":     tenant_id,
        "site_id":       site_id,
        "user_id":       user_id,
        "session_token": session_token,
        "latent_vector": latent_vector,
        "created_at":    datetime.utcnow(),
        "expires_at":    datetime.utcnow() + timedelta(minutes=expires_in_minutes),
        "last_verified": datetime.utcnow(),
        "trust_score":   1.0,
        "is_active":     True,
    }
    result = await db.sessions.insert_one(session_doc)
    return str(result.inserted_id)


async def get_session(
    db: AsyncIOMotorDatabase, session_token: str
) -> Optional[dict]:
    session = await db.sessions.find_one({
        "session_token": session_token,
        "is_active":     True,
        "expires_at":    {"$gt": datetime.utcnow()},
    })
    if session:
        session["_id"]     = str(session["_id"])
        session["user_id"] = str(session["user_id"])
    return session


async def invalidate_session(
    db: AsyncIOMotorDatabase, session_token: str
) -> None:
    await db.sessions.update_one(
        {"session_token": session_token},
        {"$set": {"is_active": False}},
    )


async def update_session_trust_score(
    db: AsyncIOMotorDatabase,
    session_token: str,
    trust_score: float,
) -> bool:
    """
    Persist the watchdog's post-decay trust score for a session.

    Called with the *updated* trust_score from WatchdogResult — i.e. after
    the watchdog has already applied its decay/recovery delta.  We never
    write a client-supplied value here.

    `last_verified` is stamped to the current UTC time so the admin dashboard
    can show how stale the heartbeat is.

    Returns True on a successful update, False when no matching active session
    was found (e.g. already invalidated by a concurrent FORCE_LOGOUT).
    """
    trust_score = max(0.0, min(1.0, trust_score))  # clamp: DB must never store out-of-range

    result = await db.sessions.update_one(
        {
            "session_token": session_token,
            "is_active":     True,   # don't silently re-open an invalidated session
        },
        {
            "$set": {
                "trust_score":   trust_score,
                "last_verified": datetime.utcnow(),
            }
        },
    )
    updated = result.matched_count > 0
    if not updated:
        logger.warning(
            "[DB] update_session_trust_score: no active session found for token …%s",
            session_token[-8:],
        )
    return updated


async def get_active_session_for_user(
    db: AsyncIOMotorDatabase,
    user_id: str,
) -> Optional[dict]:
    """
    Return the most-recently-created *active* session for a user.

    Intended for tests and admin tooling.  The /session/verify flow uses
    get_session (token-keyed) instead because it always has the token.
    """
    session = await db.sessions.find_one(
        {
            "user_id":    user_id,
            "is_active":  True,
            "expires_at": {"$gt": datetime.utcnow()},
        },
        sort=[("created_at", DESCENDING)],
    )
    if session:
        session["_id"]     = str(session["_id"])
        session["user_id"] = str(session["user_id"])
    return session


# ─────────────────────────────────────────────────────────────────────────────
# Per-User Biometric Profile Operations  (unchanged from v3.1.0)
# ─────────────────────────────────────────────────────────────────────────────

async def upsert_biometric_profile(
    db: AsyncIOMotorDatabase,
    user_id: str,
    sample_count: int,
    last_drift: float,
    adaptive_threshold: float,
    feature_means: List[float],
    selected_features: List[str],
    tenant_id:    Optional[str]        = None,
    site_id:      Optional[str]        = None,
    ema_profile:  Optional[List[float]] = None,
    ema_variance: Optional[List[float]] = None,
) -> str:
    now        = datetime.utcnow()
    set_fields = {
        "user_id":            user_id,
        "tenant_id":          tenant_id,
        "site_id":            site_id,
        "sample_count":       sample_count,
        "last_drift":         last_drift,
        "adaptive_threshold": adaptive_threshold,
        "feature_means":      feature_means,
        "selected_features":  selected_features,
        "updated_at":         now,
    }
    if ema_profile  is not None:
        set_fields["ema_profile"]  = ema_profile
    if ema_variance is not None:
        set_fields["ema_variance"] = ema_variance

    result = await db.biometric_profiles.update_one(
        {"user_id": user_id},
        {"$set": set_fields, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return str(result.upserted_id) if result.upserted_id else user_id


async def get_biometric_profile(
    db: AsyncIOMotorDatabase, user_id: str
) -> Optional[dict]:
    profile = await db.biometric_profiles.find_one({"user_id": user_id})
    if profile:
        profile["_id"] = str(profile["_id"])
    return profile


async def get_biometric_profile_summary(
    db: AsyncIOMotorDatabase, user_id: str
) -> Optional[dict]:
    profile = await db.biometric_profiles.find_one(
        {"user_id": user_id},
        {
            "user_id": 1, "sample_count": 1, "last_drift": 1,
            "adaptive_threshold": 1, "selected_features": 1,
            "updated_at": 1,
        },
    )
    if profile:
        profile["_id"] = str(profile["_id"])
    return profile


async def store_biometric_sample(
    db: AsyncIOMotorDatabase,
    user_id: str,
    theta:     float,
    h_exp:     float,
    dwell:     float,
    flight:    float,
    speed:     float,
    jitter:    float,
    accel:     float,
    rhythm:    float,
    pause:     float,
    bigram:    float,
    device_ip: str,
):
    sample = {
        "timestamp": datetime.utcnow(),
        "theta":     theta,
        "h_exp":     h_exp,
        "dwell":     dwell,
        "flight":    flight,
        "speed":     speed,
        "jitter":    jitter,
        "accel":     accel,
        "rhythm":    rhythm,
        "pause":     pause,
        "bigram":    bigram,
        "device_ip": device_ip,
    }

    ALPHA = 0.05

    async def _ema(field: str, new_val: float) -> float:
        doc = await db.biometric_profiles.find_one(
            {"user_id": user_id}, {f"avg_{field}": 1}
        )
        if doc and f"avg_{field}" in doc:
            return (1 - ALPHA) * doc[f"avg_{field}"] + ALPHA * new_val
        return new_val

    avg_theta  = await _ema("theta",  theta)
    avg_h_exp  = await _ema("h_exp",  h_exp)
    avg_dwell  = await _ema("dwell",  dwell)
    avg_flight = await _ema("flight", flight)
    avg_speed  = await _ema("speed",  speed)
    avg_jitter = await _ema("jitter", jitter)
    avg_accel  = await _ema("accel",  accel)
    avg_rhythm = await _ema("rhythm", rhythm)

    return await db.biometric_profiles.update_one(
        {"user_id": user_id},
        {
            "$push": {"samples": {"$each": [sample], "$slice": -500}},
            "$set": {
                "avg_theta":  avg_theta,
                "avg_h_exp":  avg_h_exp,
                "avg_dwell":  avg_dwell,
                "avg_flight": avg_flight,
                "avg_speed":  avg_speed,
                "avg_jitter": avg_jitter,
                "avg_accel":  avg_accel,
                "avg_rhythm": avg_rhythm,
                "updated_at": datetime.utcnow(),
            },
            "$setOnInsert": {
                "user_id":    user_id,
                "created_at": datetime.utcnow(),
            },
        },
        upsert=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Drift Event Log  (unchanged from v3.1.0)
# ─────────────────────────────────────────────────────────────────────────────

async def log_drift_event(
    db: AsyncIOMotorDatabase,
    user_id: str,
    drift_score: float,
    adaptive_threshold: float,
    trust_score: float,
    e_rec: float,
    selected_features: List[str],
    action: str,
    tenant_id:     Optional[str] = None,
    site_id:       Optional[str] = None,
    session_token: str           = "",
) -> str:
    event = {
        "user_id":            user_id,
        "tenant_id":          tenant_id,
        "site_id":            site_id,
        "timestamp":          datetime.utcnow(),
        "drift_score":        drift_score,
        "adaptive_threshold": adaptive_threshold,
        "trust_score":        trust_score,
        "e_rec":              e_rec,
        "selected_features":  selected_features,
        "action":             action,
        "session_token":      session_token,
    }
    result = await db.drift_events.insert_one(event)
    return str(result.inserted_id)


async def get_drift_events(
    db: AsyncIOMotorDatabase,
    user_id: str,
    limit: int = 50,
) -> List[dict]:
    events = await db.drift_events.find(
        {"user_id": user_id}
    ).sort("timestamp", DESCENDING).limit(limit).to_list(limit)
    for e in events:
        e["_id"] = str(e["_id"])
    return events


async def get_drift_summary(
    db: AsyncIOMotorDatabase, user_id: str
) -> dict:
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id":          "$user_id",
            "total_events": {"$sum":  1},
            "avg_drift":    {"$avg":  "$drift_score"},
            "max_drift":    {"$max":  "$drift_score"},
            "avg_trust":    {"$avg":  "$trust_score"},
            "last_event":   {"$max":  "$timestamp"},
        }},
    ]
    result = await db.drift_events.aggregate(pipeline).to_list(1)
    return result[0] if result else {}


# ─────────────────────────────────────────────────────────────────────────────
# Feature Selection History  (unchanged from v3.1.0)
# ─────────────────────────────────────────────────────────────────────────────

async def record_feature_selection(
    db: AsyncIOMotorDatabase,
    user_id: str,
    selected_features: List[str],
    feature_means: List[float],
    feature_variances: List[float],
    sample_count: int,
) -> str:
    doc = {
        "user_id":           user_id,
        "recorded_at":       datetime.utcnow(),
        "selected_features": selected_features,
        "feature_means":     feature_means,
        "feature_variances": feature_variances,
        "sample_count":      sample_count,
    }
    result = await db.feature_selections.insert_one(doc)
    return str(result.inserted_id)


async def get_feature_selection_history(
    db: AsyncIOMotorDatabase,
    user_id: str,
    limit: int = 20,
) -> List[dict]:
    docs = await db.feature_selections.find(
        {"user_id": user_id}
    ).sort("recorded_at", DESCENDING).limit(limit).to_list(limit)
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


# ─────────────────────────────────────────────────────────────────────────────
# Honeypot Operations  (unchanged from v3.1.0)
# ─────────────────────────────────────────────────────────────────────────────

async def store_honeypot_entry(
    db: AsyncIOMotorDatabase,
    user_agent: str,
    theta: float,
    ip_address: str,
    tenant_id: Optional[str] = None,
    site_id:   Optional[str] = None,
    path:    str  = "/",
    headers: dict = None,
) -> str:
    entry = {
        "tenant_id":  tenant_id,
        "site_id":    site_id,
        "timestamp":  datetime.utcnow(),
        "user_agent": user_agent,
        "theta":      theta,
        "ip_address": ip_address,
        "path":       path,
        "headers":    headers or {},
    }
    result = await db.honeypot.insert_one(entry)
    return str(result.inserted_id)


async def get_honeypot_signatures(
    db: AsyncIOMotorDatabase, limit: int = 100
) -> list:
    sigs = await db.honeypot.find().sort("timestamp", -1).limit(limit).to_list(limit)
    for s in sigs:
        s["_id"] = str(s["_id"])
    return sigs


async def get_honeypot_count(db: AsyncIOMotorDatabase) -> int:
    return await db.honeypot.count_documents({})


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup  (unchanged from v3.1.0)
# ─────────────────────────────────────────────────────────────────────────────

async def cleanup_expired_sessions(db: AsyncIOMotorDatabase) -> int:
    result = await db.sessions.delete_many(
        {"expires_at": {"$lt": datetime.utcnow()}}
    )
    return result.deleted_count