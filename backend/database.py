"""
backend/database.py  —  Unified Data-Access Layer (MongoDB / Motor)

v5.0.0 — Multi-tenant profile-build onboarding state machine.

Changes from v4.0.0
───────────────────
• BiometricProfile now carries an `onboarding_state` field
  (collecting | syncing | stable | drifted) so every consumer can
  query it without re-deriving it from raw sample counts.
• upsert_biometric_profile accepts `onboarding_state` and writes it
  atomically alongside the other summary stats.
• New helper: get_onboarding_state(db, user_id) — lightweight single-
  field read used by the heartbeat and trust-gate paths.
• New helper: set_onboarding_state(db, user_id, state) — used by the
  drift-detection path to transition stable→drifted without rewriting
  the whole profile document.
• profile_build_summary aggregate query groups per-tenant stats so the
  admin dashboard can see how many users are in each onboarding stage.
• All pre-existing behaviour is preserved; every public function is
  signature-compatible with v4.0.0.
• The `threat_intelligence` / `threat_broadcasts` collections from
  v4.0.0 are unchanged.

Onboarding state machine
────────────────────────
  collecting  — fewer than STABLE_SAMPLE_THRESHOLD samples recorded;
                drift detection is suppressed to avoid false positives
                on a cold profile.
  syncing     — sample count crossed the threshold during the current
                sync cycle; the aggregated EMA has not yet been persisted
                back.  The backend sets this transiently; the client
                transitions it to `stable` on the next successful sync.
  stable      — profile has enough samples and EMA variance is low enough
                for drift detection to be meaningful.
  drifted     — the watchdog detected a significant behavioural departure
                from the EMA baseline while the profile was `stable`.
                Re-authentication or explicit reset moves it back to
                `collecting`.

MongoDB collections modified
────────────────────────────
  biometric_profiles  — `onboarding_state` (str) field added.
                        `tenant_id` and `site_id` are now indexed for
                        per-tenant admin queries.
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

# ── Onboarding-state constants ─────────────────────────────────────────────────
ONBOARDING_COLLECTING = "collecting"
ONBOARDING_SYNCING    = "syncing"
ONBOARDING_STABLE     = "stable"
ONBOARDING_DRIFTED    = "drifted"

# Minimum aggregated samples before drift detection is armed.
# Kept here (not in the model layer) so every consumer uses one source
# of truth; callers that need it can import it directly.
STABLE_SAMPLE_THRESHOLD = 50


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
    AsyncIOMotorDatabase handle (unchanged from v4.0.0).
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

            # ── biometric_profiles ────────────────────────────────────────────
            await self.db.biometric_profiles.create_index("tenant_id")
            await self.db.biometric_profiles.create_index("site_id")
            # Fast per-tenant state-machine queries
            await self.db.biometric_profiles.create_index(
                [("tenant_id", ASCENDING), ("onboarding_state", ASCENDING)],
                name="idx_bp_tenant_state",
            )

            # ── threat_intelligence ───────────────────────────────────────────
            await self.db.threat_intelligence.create_index(
                [
                    ("fingerprint_hash", ASCENDING),
                    ("tenant_id",        ASCENDING),
                    ("action",           ASCENDING),
                ],
                unique=True,
                name="idx_ti_fp_tenant_action",
            )
            await self.db.threat_intelligence.create_index(
                [("fingerprint_hash", ASCENDING), ("expired_at", ASCENDING)],
                name="idx_ti_fp_hash",
            )
            await self.db.threat_intelligence.create_index(
                [("ip_address", ASCENDING), ("expired_at", ASCENDING)],
                name="idx_ti_ip",
            )
            await self.db.threat_intelligence.create_index(
                [("ts", ASCENDING)],
                name="idx_ti_ts",
            )

            # ── threat_broadcasts ─────────────────────────────────────────────
            await self.db.threat_broadcasts.create_index(
                [("fingerprint_hash", ASCENDING)],
                name="idx_tb_fp",
            )
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
        Insert a new threat observation or accumulate weight if a document
        already exists for the same (fingerprint_hash, tenant_id, action) triple.
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
            set_fields["ip_address"] = record.ip_address

        update_doc = {
            "$inc": {"weight": record.weight},
            "$set": set_fields,
            "$setOnInsert": {
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
        logger.warning(
            "[DB.TI] GLOBAL THREAT BROADCAST (no delivery backend configured): %s",
            json.dumps(payload, default=str),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _doc_to_threat(doc: dict) -> ThreatRecord:
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


def _derive_onboarding_state(
    sample_count: int,
    current_state: str,
    last_drift: float = 0.0,
    adaptive_threshold: float = 1.8,
) -> str:
    """
    Pure function: derive the correct onboarding state from profile facts.

    Rules (ordered by priority):
      1. If the stored state is already `drifted`, keep it — only an explicit
         reset or a re-auth clears it.
      2. If sample_count < STABLE_SAMPLE_THRESHOLD → `collecting`.
      3. If sample_count >= threshold and drift is already above the adaptive
         threshold (and we were previously stable) → `drifted`.
      4. Otherwise → `stable`.

    The `syncing` state is a transient backend flag set during an in-progress
    upsert; callers set it directly via set_onboarding_state() and it is
    immediately overwritten by the next completed sync.
    """
    if current_state == ONBOARDING_DRIFTED:
        return ONBOARDING_DRIFTED
    if sample_count < STABLE_SAMPLE_THRESHOLD:
        return ONBOARDING_COLLECTING
    if (
        current_state == ONBOARDING_STABLE
        and adaptive_threshold > 0
        and last_drift > adaptive_threshold
    ):
        return ONBOARDING_DRIFTED
    return ONBOARDING_STABLE


# ─────────────────────────────────────────────────────────────────────────────
# Tenant & Site Operations  (unchanged from v4.0.0)
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
# User Operations  (unchanged from v4.0.0)
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
# Session Operations  (unchanged from v4.0.0)
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
    trust_score = max(0.0, min(1.0, trust_score))

    result = await db.sessions.update_one(
        {
            "session_token": session_token,
            "is_active":     True,
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
# Per-User Biometric Profile Operations
# ─────────────────────────────────────────────────────────────────────────────

async def upsert_biometric_profile(
    db: AsyncIOMotorDatabase,
    user_id: str,
    sample_count: int,
    last_drift: float,
    adaptive_threshold: float,
    feature_means: List[float],
    selected_features: List[str],
    tenant_id:         Optional[str]        = None,
    site_id:           Optional[str]        = None,
    ema_profile:       Optional[List[float]] = None,
    ema_variance:      Optional[List[float]] = None,
    onboarding_state:  Optional[str]        = None,
) -> str:
    """
    Upsert the aggregated biometric profile for a user.

    `onboarding_state` is derived automatically if not provided by the caller,
    using the current document's stored state so that the `drifted` sticky
    rule is respected.  Callers that want to force a transition (e.g.
    reset after re-auth) should pass the desired state explicitly.

    Only aggregated statistics are stored — raw keystroke / mouse traces
    are never persisted to MongoDB.
    """
    now = datetime.utcnow()

    # Fetch the current state before overwriting so _derive_onboarding_state
    # can apply the sticky-drifted rule.
    existing = await db.biometric_profiles.find_one(
        {"user_id": user_id}, {"onboarding_state": 1}
    )
    current_state = (existing or {}).get("onboarding_state", ONBOARDING_COLLECTING)

    if onboarding_state is None:
        onboarding_state = _derive_onboarding_state(
            sample_count        = sample_count,
            current_state       = current_state,
            last_drift          = last_drift,
            adaptive_threshold  = adaptive_threshold,
        )

    set_fields: dict = {
        "user_id":            user_id,
        "tenant_id":          tenant_id,
        "site_id":            site_id,
        "sample_count":       sample_count,
        "last_drift":         last_drift,
        "adaptive_threshold": adaptive_threshold,
        "feature_means":      feature_means,
        "selected_features":  selected_features,
        "onboarding_state":   onboarding_state,
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

    logger.debug(
        "[DB.BP] upsert user=%s samples=%d state=%s drift=%.3f",
        user_id, sample_count, onboarding_state, last_drift,
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
            "onboarding_state": 1, "updated_at": 1,
        },
    )
    if profile:
        profile["_id"] = str(profile["_id"])
    return profile


async def get_onboarding_state(
    db: AsyncIOMotorDatabase, user_id: str
) -> str:
    """
    Lightweight single-field read.  Returns `collecting` for unknown users
    so callers treat them as pre-onboarding (drift detection suppressed).
    """
    doc = await db.biometric_profiles.find_one(
        {"user_id": user_id}, {"onboarding_state": 1}
    )
    if not doc:
        return ONBOARDING_COLLECTING
    return doc.get("onboarding_state", ONBOARDING_COLLECTING)


async def set_onboarding_state(
    db: AsyncIOMotorDatabase,
    user_id: str,
    state: str,
) -> bool:
    """
    Atomically overwrite the onboarding state without touching other fields.
    Used by the drift-detection path (stable → drifted) and the reset path
    (drifted → collecting) without triggering a full profile re-computation.

    Returns True when a document was matched.
    """
    if state not in (
        ONBOARDING_COLLECTING,
        ONBOARDING_SYNCING,
        ONBOARDING_STABLE,
        ONBOARDING_DRIFTED,
    ):
        raise ValueError(f"Unknown onboarding state: {state!r}")

    result = await db.biometric_profiles.update_one(
        {"user_id": user_id},
        {"$set": {"onboarding_state": state, "updated_at": datetime.utcnow()}},
    )
    matched = result.matched_count > 0
    if matched:
        logger.info("[DB.BP] onboarding_state → %s for user=%s", state, user_id)
    return matched


async def reset_biometric_profile(
    db: AsyncIOMotorDatabase,
    user_id: str,
    tenant_id: Optional[str] = None,
    site_id:   Optional[str] = None,
) -> None:
    """
    Reset a profile back to the `collecting` state after re-authentication.
    Wipes sample_count, EMA vectors, and drift history so the new session
    builds a clean baseline rather than inheriting stale variance.

    The document is preserved (not deleted) for audit purposes; the old
    EMA data is overwritten in-place.
    """
    now = datetime.utcnow()
    await db.biometric_profiles.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "sample_count":       0,
                "last_drift":         0.0,
                "adaptive_threshold": 1.8,
                "feature_means":      [0.5] * 8,
                "selected_features":  [],
                "ema_profile":        None,
                "ema_variance":       None,
                "onboarding_state":   ONBOARDING_COLLECTING,
                "reset_at":           now,
                "updated_at":         now,
            }
        },
        upsert=True,
    )
    logger.info("[DB.BP] Profile reset → collecting for user=%s", user_id)


async def profile_build_summary(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
) -> dict:
    """
    Per-tenant admin aggregate: how many users are in each onboarding state.
    Safe to call on large collections — uses the idx_bp_tenant_state index.
    """
    pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {
            "_id":   "$onboarding_state",
            "count": {"$sum": 1},
            "avg_samples": {"$avg": "$sample_count"},
        }},
    ]
    rows = await db.biometric_profiles.aggregate(pipeline).to_list(20)
    return {row["_id"]: {"count": row["count"], "avg_samples": row["avg_samples"]} for row in rows}


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
    """
    Maintain a rolling EMA of the 8 biometric channels.

    Raw values are NOT stored in MongoDB; only the rolling EMA is updated.
    The client-side ring buffer retains up to 500 samples for local
    drift computation; none of that data is transmitted to the server.
    """
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
                "user_id":          user_id,
                "onboarding_state": ONBOARDING_COLLECTING,
                "created_at":       datetime.utcnow(),
            },
        },
        upsert=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Drift Event Log  (unchanged from v4.0.0)
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
# Feature Selection History  (unchanged from v4.0.0)
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
# Honeypot Operations  (unchanged from v4.0.0)
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
# Cleanup  (unchanged from v4.0.0)
# ─────────────────────────────────────────────────────────────────────────────

async def cleanup_expired_sessions(db: AsyncIOMotorDatabase) -> int:
    result = await db.sessions.delete_many(
        {"expires_at": {"$lt": datetime.utcnow()}}
    )
    return result.deleted_count