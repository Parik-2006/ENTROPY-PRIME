"""
MongoDB Connection and Database Operations for Entropy Prime
"""
import os
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from bson import ObjectId
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# MongoDB Connection
# ─────────────────────────────────────────────────────────────────────────────
class Database:
    """Async MongoDB database handler"""
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
    
    async def connect_to_mongo(self):
        """Connect to MongoDB"""
        mongo_url = os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("MONGODB_DB_NAME", "entropy_prime")
        
        self.client = AsyncIOMotorClient(mongo_url)
        self.db = self.client[db_name]
        
        # Create indexes
        await self._create_indexes()
        print(f"✓ Connected to MongoDB: {db_name}")
    
    async def close_mongo_connection(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            print("✓ MongoDB connection closed")
    
    async def _create_indexes(self):
        """Create database indexes for performance"""
        # Users collection
        await self.db.users.create_index("email", unique=True)
        await self.db.users.create_index([("created_at", DESCENDING)])
        
        # Sessions collection
        await self.db.sessions.create_index("session_token", unique=True)
        await self.db.sessions.create_index("user_id")
        await self.db.sessions.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)  # TTL
        
        # Honeypot collection
        await self.db.honeypot.create_index([("timestamp", DESCENDING)])
        await self.db.honeypot.create_index("ip_address")
        
        # Biometric profiles
        await self.db.biometric_profiles.create_index("user_id", unique=True)

# ─────────────────────────────────────────────────────────────────────────────
# User Operations
# ─────────────────────────────────────────────────────────────────────────────
async def user_exists(db: AsyncIOMotorDatabase, email: str) -> bool:
    """Check if user already exists"""
    user = await db.users.find_one({"email": email.lower()})
    return user is not None

async def create_user(db: AsyncIOMotorDatabase, email: str, password_hash: str) -> str:
    """Create new user with hashed password"""
    user_doc = {
        "email": email.lower(),
        "password_hash": password_hash,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "last_login": None,
        "is_active": True,
        "security_level": "standard",
        "biometric_profile": {}
    }
    result = await db.users.insert_one(user_doc)
    return str(result.inserted_id)

async def get_user_by_email(db: AsyncIOMotorDatabase, email: str) -> Optional[dict]:
    """Retrieve user by email"""
    user = await db.users.find_one({"email": email.lower()})
    if user:
        user["_id"] = str(user["_id"])
    return user

async def get_user_by_id(db: AsyncIOMotorDatabase, user_id: str) -> Optional[dict]:
    """Retrieve user by ID"""
    try:
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if user:
            user["_id"] = str(user["_id"])
        return user
    except Exception:
        return None

async def update_last_login(db: AsyncIOMotorDatabase, user_id: str):
    """Update last login timestamp"""
    try:
        await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"last_login": datetime.utcnow()}}
        )
    except Exception:
        pass

async def update_user_security_level(db: AsyncIOMotorDatabase, user_id: str, level: str):
    """Update user security level (economy, standard, hard, punisher)"""
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
    expires_in_minutes: int = 30
) -> str:
    """Create a new session"""
    session_doc = {
        "user_id": user_id,
        "session_token": session_token,
        "latent_vector": latent_vector,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(minutes=expires_in_minutes),
        "last_verified": datetime.utcnow(),
        "trust_score": 1.0,
        "is_active": True
    }
    result = await db.sessions.insert_one(session_doc)
    return str(result.inserted_id)

async def get_session(db: AsyncIOMotorDatabase, session_token: str) -> Optional[dict]:
    """Retrieve active session"""
    session = await db.sessions.find_one({
        "session_token": session_token,
        "is_active": True,
        "expires_at": {"$gt": datetime.utcnow()}
    })
    if session:
        session["_id"] = str(session["_id"])
        session["user_id"] = str(session["user_id"])
    return session

async def invalidate_session(db: AsyncIOMotorDatabase, session_token: str):
    """Invalidate a session"""
    await db.sessions.update_one(
        {"session_token": session_token},
        {"$set": {"is_active": False}}
    )

async def update_session_trust_score(db: AsyncIOMotorDatabase, session_token: str, trust_score: float):
    """Update session trust score"""
    await db.sessions.update_one(
        {"session_token": session_token},
        {"$set": {
            "trust_score": trust_score,
            "last_verified": datetime.utcnow()
        }}
    )

# ─────────────────────────────────────────────────────────────────────────────
# Biometric Operations
# ─────────────────────────────────────────────────────────────────────────────
async def store_biometric_sample(
    db: AsyncIOMotorDatabase,
    user_id: str,
    theta: float,
    h_exp: float,
    dwell: float,
    flight: float,
    speed: float,
    jitter: float,
    device_ip: str
):
    """Store biometric sample for a user"""
    sample = {
        "timestamp": datetime.utcnow(),
        "theta": theta,
        "h_exp": h_exp,
        "dwell": dwell,
        "flight": flight,
        "speed": speed,
        "jitter": jitter,
        "device_ip": device_ip
    }
    
    # Upsert: create or update biometric profile
    avg_theta = theta * 0.1 + (0.9 * (await _get_biometric_avg(db, user_id, "theta")))
    avg_h_exp = h_exp * 0.1 + (0.9 * (await _get_biometric_avg(db, user_id, "h_exp")))
    
    result = await db.biometric_profiles.update_one(
        {"user_id": user_id},
        {
            "$push": {"samples": sample},
            "$set": {
                "avg_theta": avg_theta,
                "avg_h_exp": avg_h_exp,
                "updated_at": datetime.utcnow()
            },
            "$setOnInsert": {
                "user_id": user_id,
                "created_at": datetime.utcnow()
            }
        },
        upsert=True
    )
    return result

async def _get_biometric_avg(db: AsyncIOMotorDatabase, user_id: str, field: str) -> float:
    """Helper to get current biomet average"""
    profile = await db.biometric_profiles.find_one(
        {"user_id": user_id},
        {"avg_" + field: 1}
    )
    if profile:
        return profile.get("avg_" + field, 0.5)
    return 0.5

async def get_biometric_profile(db: AsyncIOMotorDatabase, user_id: str) -> Optional[dict]:
    """Retrieve biometric profile"""
    profile = await db.biometric_profiles.find_one({"user_id": user_id})
    if profile:
        profile["_id"] = str(profile["_id"])
    return profile

# ─────────────────────────────────────────────────────────────────────────────
# Honeypot Operations
# ─────────────────────────────────────────────────────────────────────────────
async def store_honeypot_entry(
    db: AsyncIOMotorDatabase,
    user_agent: str,
    theta: float,
    ip_address: str,
    path: str = "/",
    headers: dict = None
):
    """Store honeypot bot signature"""
    entry = {
        "timestamp": datetime.utcnow(),
        "user_agent": user_agent,
        "theta": theta,
        "ip_address": ip_address,
        "path": path,
        "headers": headers or {}
    }
    result = await db.honeypot.insert_one(entry)
    return str(result.inserted_id)

async def get_honeypot_signatures(db: AsyncIOMotorDatabase, limit: int = 100) -> list:
    """Retrieve honeypot signatures"""
    signatures = await db.honeypot.find().sort("timestamp", -1).limit(limit).to_list(limit)
    for sig in signatures:
        sig["_id"] = str(sig["_id"])
    return signatures

async def get_honeypot_count(db: AsyncIOMotorDatabase) -> int:
    """Get total honeypot entries count"""
    return await db.honeypot.count_documents({})

# ─────────────────────────────────────────────────────────────────────────────
# Cleanup Operations
# ─────────────────────────────────────────────────────────────────────────────
async def cleanup_expired_sessions(db: AsyncIOMotorDatabase):
    """Remove expired sessions (optional, TTL index handles this)"""
    result = await db.sessions.delete_many({
        "expires_at": {"$lt": datetime.utcnow()}
    })
    return result.deleted_count
