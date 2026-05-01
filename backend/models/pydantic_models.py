"""
MongoDB Schemas and Pydantic Models for Entropy Prime
Separated from models/__init__.py to avoid circular imports with pipeline.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId


class UserCreate(BaseModel):
    email: EmailStr
    plain_password: str

    class Config:
        json_schema_extra = {
            "example": {"email": "user@example.com", "plain_password": "securepassword123"}
        }


class UserLogin(BaseModel):
    email: EmailStr
    plain_password: str


class User(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    email: str
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    biometric_profile: dict = Field(default_factory=dict)
    is_active: bool = True
    security_level: str = "standard"

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda v: v.isoformat()}


class UserResponse(BaseModel):
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
        json_encoders = {ObjectId: str, datetime: lambda v: v.isoformat()}


class Session(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    session_token: str
    latent_vector: List[float] = Field(default_factory=lambda: [0.0]*32)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    last_verified: Optional[datetime] = None
    trust_score: float = 1.0
    is_active: bool = True

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda v: v.isoformat()}


class AuthResponse(BaseModel):
    session_token: str
    user_id: str
    email: str
    security_level: str
    expires_in: int


class PasswordHashResponse(BaseModel):
    hash: str
    action: str
    elapsed_ms: float
    argon2_params: dict
    confidence: str
    fallback: bool
