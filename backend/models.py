"""
MongoDB Schemas and Models for Entropy Prime
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId

# ─────────────────────────────────────────────────────────────────────────────
# User Model
# ─────────────────────────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    """User registration request"""
    email: EmailStr
    plain_password: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "plain_password": "securepassword123"
            }
        }

class UserLogin(BaseModel):
    """User login request"""
    email: EmailStr
    plain_password: str

class User(BaseModel):
    """User document in MongoDB"""
    id: Optional[str] = Field(default=None, alias="_id")
    email: str
    password_hash: str  # Argon2id hash
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    biometric_profile: dict = Field(default_factory=dict)  # Stores CNN biometric data
    is_active: bool = True
    security_level: str = "standard"  # economy, standard, hard, punisher
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }

class UserResponse(BaseModel):
    """User response (no password hash)"""
    id: Optional[str] = Field(None, alias="_id")
    email: str
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime]
    is_active: bool
    security_level: str
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }

# ─────────────────────────────────────────────────────────────────────────────
# Session Model
# ─────────────────────────────────────────────────────────────────────────────
class Session(BaseModel):
    """Session document in MongoDB"""
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str  # Reference to User._id
    session_token: str
    latent_vector: List[float] = Field(default_factory=lambda: [0.0]*32)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime  # 30 minutes from creation
    last_verified: Optional[datetime] = None
    trust_score: float = 1.0
    is_active: bool = True
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }

# ─────────────────────────────────────────────────────────────────────────────
# Biometric Profile Model
# ─────────────────────────────────────────────────────────────────────────────
class BiometricSample(BaseModel):
    """Individual biometric sample"""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    theta: float  # Humanity score from CNN
    h_exp: float  # Entropy score
    dwell: float
    flight: float
    speed: float
    jitter: float
    device_ip: str

class BiometricProfile(BaseModel):
    """Biometric profile stored per user"""
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    samples: List[BiometricSample] = Field(default_factory=list)
    avg_theta: float = 0.5
    avg_h_exp: float = 0.5
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True

# ─────────────────────────────────────────────────────────────────────────────
# Honeypot Entry Model
# ─────────────────────────────────────────────────────────────────────────────
class HoneypotEntry(BaseModel):
    """Honeypot signature stored in MongoDB"""
    id: Optional[str] = Field(default=None, alias="_id")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_agent: str
    theta: float  # Low humanity score indicating bot
    ip_address: str
    path: str = "/"
    headers: dict = Field(default_factory=dict)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }

# ─────────────────────────────────────────────────────────────────────────────
# Authentication Response Models
# ─────────────────────────────────────────────────────────────────────────────
class AuthResponse(BaseModel):
    """Authentication response"""
    session_token: str
    user_id: str
    email: str
    security_level: str
    expires_in: int  # seconds

class PasswordHashResponse(BaseModel):
    """RL-hardened password hash response"""
    hash: str
    action: str
    elapsed_ms: float
    argon2_params: dict
