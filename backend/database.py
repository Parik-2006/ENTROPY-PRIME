"""
MongoDB Connection and Database Operations for Entropy Prime
Includes per-user biometric profile: feature selection, drift tracking, behavioral pattern storage.
Production-ready with connection pooling and retry logic.

v3.1.0 changes
──────────────
• update_session_trust_score: now accepts the *post-decay* trust score from
  the watchdog and writes it atomically with `last_verified`.  The previous
  implementation wrote the client-supplied score, which could be inflated.
• get_active_session_for_user: new helper — returns the most-recently-created
  active session for a given user_id.  Used by tests and admin tooling; the
  /session/verify flow uses get_session (token-keyed lookup) instead.
• No other behaviour changes.
"""
import os
import logging
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
from bson import ObjectId
from typing import Optional, List

logger = logging.getLogger("entropy_prime.database")

# ─────────────────────────────────────────────────────────────────────────────
# MongoDB Connection with Connection Pooling
# ─────────────────────────────────────────────────────────────────────────────
class Database:
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.max_retries = 5
        self.retry_delay = 2

    async def connect_to_mongo(self):
        """Connect to MongoDB with retry logic. Falls back to mongomock for development."""
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
                await self.client.admin.command('ping')
                self.db = self.client[db_name]
                await self._create_indexes()
                logger.info(f"✓ Connected to MongoDB: {db_name}")
                return
            except (ServerSelectionTimeoutError, ConnectionFailure) as e:
                logger.warning(f"Connection attempt {attempt}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.warning(f"Failed to connect to real MongoDB after {self.max_retries} attempts")
                    logger.info("Falling back to mongomock (in-memory) for development...")
                    try:
                        import mongomock
                        sync_client = mongomock.MongoClient()
                        self.client = sync_client
                        self.db = sync_client[db_name]
                        logger.info(f"✓ Using mongomock database: {db_name} (development/test mode)")
                        return
                    except Exception as mock_err:
                        logger.error(f"Failed to initialize mongomock: {mock_err}")
                        raise

    async def close_mongo_connection(self):
        if self.client:
            self.client.close()
            logger.info("✓ MongoDB connection closed")

    async def _create_indexes(self):
        """Create database indexes for performance and data integrity."""
        try:
            await self.db.users.create_index("email", unique=True)
            await self.db.users.create_index([("created_at", DESCENDING)])
            await self.db.sessions.create_index("session_token", unique=True)
            await self.db.sessions.create_index("user_id")
            await self.db.sessions.create_index(
                [("expires_at", ASCENDING)], expireAfterSeconds=0
            )
            await self.db.honeypot.create_index([("timestamp", DESCENDING)])
            await self.db.honeypot.create_index("ip_address")
            await self.db.biometric_profiles.create_index("user_id", unique=True)
            await self.db.biometric_profiles.create_index([("updated_at", DESCENDING)])
            await self.db.drift_events.create_index("user_id")
            await self.db.drift_events.create_index([("timestamp", DESCENDING)])
            await self.db.drift_events.create_index(
                [("timestamp", ASCENDING)], expireAfterSeconds=60 * 60 * 24 * 30
            )
            await self.db.feature_selections.create_index("user_id")
            await self.db.feature_selections.create_index([("recorded_at", DESCENDING)])
            logger.info("✓ All database indexes created")
        except Exception as e:
            logger.error(f"Index creation error: {e}", exc_info=True)
            raise

# ─────────────────────────────────────────────────────────────────────────────
# User Operations
# ─────────────────────────────────────────────────────────────────────────────
async def user_exists(db: AsyncIOMotorDatabase, email: str) -> bool:
    return await db.users.find_one({"email": email.lower()}) is not None

async def create_user(db: AsyncIOMotorDatabase, email: str, password_hash: str) -> str:
    user_doc = {
        "email":          email.lower(),
        "password_hash":  password_hash,
        "created_at":     datetime.utcnow(),
        "updated_at":     datetime.utcnow(),
        "last_login":     None,
        "is_active":      True,
        "security_level": "standard",
        "biometric_profile": {},
    }
    result = await db.users.insert_one(user_doc)
    return str(result.inserted_id)

async def get_user_by_email(db: AsyncIOMotorDatabase, email: str) -> Optional[dict]:
    user = await db.users.find_one({"email": email.lower()})
    if user:
        user["_id"] = str(user["_id"])
    return user

async def get_user_by_id(db: AsyncIOMotorDatabase, user_id: str) -> Optional[dict]:
    try:
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if user:
            user["_id"] = str(user["_id"])
        return user
    except Exception:
        return None

async def update_last_login(db: AsyncIOMotorDatabase, user_id: str):
    try:
        await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"last_login": datetime.utcnow()}}
        )
    except Exception:
        pass

async def update_user_security_level(db: AsyncIOMotorDatabase, user_id: str, level: str):
    try:
        await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"security_level": level, "updated_at": datetime.utcnow()}}
        )
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# Session Operations
# ─────────────────────────────────────────────────────────────────────────────
async def create_session(
    db: AsyncIOMotorDatabase,
    user_id: str,
    session_token: str,
    latent_vector: list,
    expires_in_minutes: int = 30,
) -> str:
    session_doc = {
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

async def get_session(db: AsyncIOMotorDatabase, session_token: str) -> Optional[dict]:
    session = await db.sessions.find_one({
        "session_token": session_token,
        "is_active":     True,
        "expires_at":    {"$gt": datetime.utcnow()},
    })
    if session:
        session["_id"]     = str(session["_id"])
        session["user_id"] = str(session["user_id"])
    return session

async def invalidate_session(db: AsyncIOMotorDatabase, session_token: str):
    await db.sessions.update_one(
        {"session_token": session_token},
        {"$set": {"is_active": False}}
    )

async def update_session_trust_score(
    db: AsyncIOMotorDatabase,
    session_token: str,
    trust_score: float,
) -> bool:
    """
    Persist the watchdog's post-decay trust score for a session.

    This is called with the *updated* trust score returned by
    WatchdogResult.trust_score — i.e. after the watchdog has already applied
    its decay / recovery delta.  We never write a client-supplied value here.

    `last_verified` is stamped to the current UTC time so the admin dashboard
    can show how stale the heartbeat is.

    Returns True on a successful update, False when no matching active session
    was found (e.g. already invalidated by a concurrent FORCE_LOGOUT).
    """
    trust_score = max(0.0, min(1.0, trust_score))   # clamp: DB must never store out-of-range

    result = await db.sessions.update_one(
        {
            "session_token": session_token,
            "is_active":     True,    # don't silently re-open an invalidated session
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
            "user_id":   user_id,
            "is_active": True,
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
    ema_profile: Optional[List[float]] = None,
    ema_variance: Optional[List[float]] = None,
) -> str:
    now = datetime.utcnow()
    update_doc = {
        "$set": {
            "user_id":           user_id,
            "sample_count":      sample_count,
            "last_drift":        last_drift,
            "adaptive_threshold": adaptive_threshold,
            "feature_means":     feature_means,
            "selected_features": selected_features,
            "updated_at":        now,
        },
        "$setOnInsert": {
            "created_at": now,
        },
    }
    if ema_profile is not None:
        update_doc["$set"]["ema_profile"]  = ema_profile
    if ema_variance is not None:
        update_doc["$set"]["ema_variance"] = ema_variance

    result = await db.biometric_profiles.update_one(
        {"user_id": user_id},
        update_doc,
        upsert=True,
    )
    return str(result.upserted_id) if result.upserted_id else user_id

async def get_biometric_profile(db: AsyncIOMotorDatabase, user_id: str) -> Optional[dict]:
    profile = await db.biometric_profiles.find_one({"user_id": user_id})
    if profile:
        profile["_id"] = str(profile["_id"])
    return profile

async def get_biometric_profile_summary(db: AsyncIOMotorDatabase, user_id: str) -> Optional[dict]:
    profile = await db.biometric_profiles.find_one(
        {"user_id": user_id},
        {
            "user_id": 1, "sample_count": 1, "last_drift": 1,
            "adaptive_threshold": 1, "selected_features": 1,
            "updated_at": 1,
        }
    )
    if profile:
        profile["_id"] = str(profile["_id"])
    return profile

async def store_biometric_sample(
    db: AsyncIOMotorDatabase,
    user_id: str,
    theta: float,
    h_exp: float,
    dwell: float,
    flight: float,
    speed: float,
    jitter: float,
    accel: float,
    rhythm: float,
    pause: float,
    bigram: float,
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
        profile = await db.biometric_profiles.find_one(
            {"user_id": user_id}, {f"avg_{field}": 1}
        )
        if profile and f"avg_{field}" in profile:
            return (1 - ALPHA) * profile[f"avg_{field}"] + ALPHA * new_val
        return new_val

    avg_theta  = await _ema("theta",  theta)
    avg_h_exp  = await _ema("h_exp",  h_exp)
    avg_dwell  = await _ema("dwell",  dwell)
    avg_flight = await _ema("flight", flight)
    avg_speed  = await _ema("speed",  speed)
    avg_jitter = await _ema("jitter", jitter)
    avg_accel  = await _ema("accel",  accel)
    avg_rhythm = await _ema("rhythm", rhythm)

    result = await db.biometric_profiles.update_one(
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
    return result

# ─────────────────────────────────────────────────────────────────────────────
# Drift Event Log
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
    session_token: str = "",
):
    event = {
        "user_id":           user_id,
        "timestamp":         datetime.utcnow(),
        "drift_score":       drift_score,
        "adaptive_threshold": adaptive_threshold,
        "trust_score":       trust_score,
        "e_rec":             e_rec,
        "selected_features": selected_features,
        "action":            action,
        "session_token":     session_token,
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

async def get_drift_summary(db: AsyncIOMotorDatabase, user_id: str) -> dict:
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id":               "$user_id",
            "total_events":      {"$sum": 1},
            "avg_drift":         {"$avg": "$drift_score"},
            "max_drift":         {"$max": "$drift_score"},
            "avg_trust":         {"$avg": "$trust_score"},
            "last_event":        {"$max": "$timestamp"},
        }},
    ]
    result = await db.drift_events.aggregate(pipeline).to_list(1)
    return result[0] if result else {}

# ─────────────────────────────────────────────────────────────────────────────
# Feature Selection History
# ─────────────────────────────────────────────────────────────────────────────

async def record_feature_selection(
    db: AsyncIOMotorDatabase,
    user_id: str,
    selected_features: List[str],
    feature_means: List[float],
    feature_variances: List[float],
    sample_count: int,
):
    doc = {
        "user_id":          user_id,
        "recorded_at":      datetime.utcnow(),
        "selected_features": selected_features,
        "feature_means":    feature_means,
        "feature_variances": feature_variances,
        "sample_count":     sample_count,
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
# Honeypot Operations
# ─────────────────────────────────────────────────────────────────────────────

async def store_honeypot_entry(
    db: AsyncIOMotorDatabase,
    user_agent: str,
    theta: float,
    ip_address: str,
    path: str = "/",
    headers: dict = None,
):
    entry = {
        "timestamp":  datetime.utcnow(),
        "user_agent": user_agent,
        "theta":      theta,
        "ip_address": ip_address,
        "path":       path,
        "headers":    headers or {},
    }
    result = await db.honeypot.insert_one(entry)
    return str(result.inserted_id)

async def get_honeypot_signatures(db: AsyncIOMotorDatabase, limit: int = 100) -> list:
    sigs = await db.honeypot.find().sort("timestamp", -1).limit(limit).to_list(limit)
    for s in sigs:
        s["_id"] = str(s["_id"])
    return sigs

async def get_honeypot_count(db: AsyncIOMotorDatabase) -> int:
    return await db.honeypot.count_documents({})

# ─────────────────────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────────────────────

async def cleanup_expired_sessions(db: AsyncIOMotorDatabase):
    result = await db.sessions.delete_many({"expires_at": {"$lt": datetime.utcnow()}})
    return result.deleted_count
