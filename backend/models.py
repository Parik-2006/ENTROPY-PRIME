"""
MongoDB Schemas and Pydantic Models for Entropy Prime
Includes per-user biometric profile: feature selection, drift tracking, EMA behavioral pattern.
"""
from typing import Optional, List, Dict
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId

# ─────────────────────────────────────────────────────────────────────────────
# Feature Names (must match biometrics.js FEATURE_NAMES)
# ─────────────────────────────────────────────────────────────────────────────
FEATURE_NAMES = [
    "dwell_norm",
    "flight_norm",
    "speed_norm",
    "jitter_norm",
    "accel_norm",
    "rhythm_norm",
    "pause_norm",
    "bigram_norm",
]

# ─────────────────────────────────────────────────────────────────────────────
# User Models
# ─────────────────────────────────────────────────────────────────────────────
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
    id: Optional[str]  = Field(default=None, alias="_id")
    email: str
    password_hash: str
    created_at: datetime  = Field(default_factory=datetime.utcnow)
    updated_at: datetime  = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
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

# ─────────────────────────────────────────────────────────────────────────────
# Session Models
# ─────────────────────────────────────────────────────────────────────────────
class Session(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    session_token: str
    latent_vector: List[float] = Field(default_factory=lambda: [0.0] * 32)
    created_at: datetime  = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    last_verified: Optional[datetime] = None
    trust_score: float = 1.0
    is_active: bool = True

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda v: v.isoformat()}

# ─────────────────────────────────────────────────────────────────────────────
# Per-User Biometric Profile Models
# ─────────────────────────────────────────────────────────────────────────────

class BiometricSample(BaseModel):
    """Single 8-channel biometric sample."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    theta:  float
    h_exp:  float
    dwell:  float
    flight: float
    speed:  float
    jitter: float
    accel:  float
    rhythm: float
    pause:  float
    bigram: float
    device_ip: str

class FeatureSelectorState(BaseModel):
    """
    Per-user online feature selector state.
    Tracks Welford running mean/variance for each of the 8 features
    and exposes the top-K selected feature indices.
    """
    means:    List[float] = Field(default_factory=lambda: [0.5] * 8)
    m2s:      List[float] = Field(default_factory=lambda: [0.1] * 8)  # M2 accumulator
    n:        int          = 0
    selected: List[int]   = Field(default_factory=lambda: list(range(8)))  # top-K indices
    k:        int          = 6

    def selected_feature_names(self) -> List[str]:
        return [FEATURE_NAMES[i] for i in self.selected if i < len(FEATURE_NAMES)]

class BehavioralProfileState(BaseModel):
    """
    Per-user EMA behavioral profile.
    Tracks the user's stable behavioral pattern and detects drift.
    """
    ema_profile:   Optional[List[float]] = None  # 8-dim EMA mean
    ema_variance:  Optional[List[float]] = None  # 8-dim EMA variance
    sample_count:  int   = 0
    drift_history: List[float] = Field(default_factory=list)  # last 100 drift scores
    last_drift:    float = 0.0

    @property
    def adaptive_threshold(self) -> float:
        if len(self.drift_history) < 10:
            return 0.18 * 10
        mean = sum(self.drift_history) / len(self.drift_history)
        variance = sum((v - mean) ** 2 for v in self.drift_history) / len(self.drift_history)
        std  = variance ** 0.5
        return mean + 2 * std

    @property
    def is_drifting(self) -> bool:
        return self.sample_count > 20 and self.last_drift > self.adaptive_threshold

class BiometricProfile(BaseModel):
    """
    Full per-user biometric profile stored in MongoDB.
    Combines raw sample history, per-user feature selector, and behavioral EMA pattern.
    """
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str

    # Per-user feature selector state (Welford online stats)
    feature_selector: FeatureSelectorState = Field(default_factory=FeatureSelectorState)

    # Per-user behavioral EMA profile
    behavioral_profile: BehavioralProfileState = Field(default_factory=BehavioralProfileState)

    # Rolling averages (EMA, alpha=0.05) per channel
    avg_theta:  float = 0.5
    avg_h_exp:  float = 0.5
    avg_dwell:  float = 0.5
    avg_flight: float = 0.5
    avg_speed:  float = 0.5
    avg_jitter: float = 0.5
    avg_accel:  float = 0.5
    avg_rhythm: float = 0.5

    # Summary stats (updated on each sync)
    sample_count:      int   = 0
    last_drift:        float = 0.0
    adaptive_threshold: float = 1.8
    selected_features: List[str] = Field(default_factory=list)
    feature_means:     List[float] = Field(default_factory=lambda: [0.5] * 8)

    # Raw sample ring buffer (last 500)
    samples: List[BiometricSample] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True

# ─────────────────────────────────────────────────────────────────────────────
# Drift Event Model
# ─────────────────────────────────────────────────────────────────────────────
class DriftEvent(BaseModel):
    """Single drift detection event logged for forensics."""
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    drift_score:        float
    adaptive_threshold: float
    trust_score:        float
    e_rec:              float
    selected_features:  List[str]
    action:             str   # ok | passive_reauth | disable_sensitive_apis
    session_token:      str   = ""

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda v: v.isoformat()}

class DriftSummary(BaseModel):
    """Aggregated drift statistics for a user."""
    user_id:      str
    total_events: int
    avg_drift:    float
    max_drift:    float
    avg_trust:    float
    last_event:   Optional[datetime]

# ─────────────────────────────────────────────────────────────────────────────
# Feature Selection History Model
# ─────────────────────────────────────────────────────────────────────────────
class FeatureSelectionSnapshot(BaseModel):
    """Point-in-time snapshot of per-user feature selection."""
    id: Optional[str] = Field(default=None, alias="_id")
    user_id:           str
    recorded_at:       datetime = Field(default_factory=datetime.utcnow)
    selected_features: List[str]
    feature_means:     List[float]
    feature_variances: List[float]
    sample_count:      int

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda v: v.isoformat()}

# ─────────────────────────────────────────────────────────────────────────────
# Honeypot Model
# ─────────────────────────────────────────────────────────────────────────────
class HoneypotEntry(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    timestamp:  datetime = Field(default_factory=datetime.utcnow)
    user_agent: str
    theta:      float
    ip_address: str
    path:       str = "/"
    headers:    dict = Field(default_factory=dict)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda v: v.isoformat()}

# ─────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ─────────────────────────────────────────────────────────────────────────────
class AuthResponse(BaseModel):
    session_token:  str
    user_id:        str
    email:          str
    security_level: str
    expires_in:     int

class PasswordHashResponse(BaseModel):
    hash:          str
    action:        str
    elapsed_ms:    float
    argon2_params: dict

class BiometricProfileUpdateRequest(BaseModel):
    """Payload from browser biometric sync."""
    user_id:            str
    sample_count:       int
    last_drift:         float
    adaptive_threshold: float
    feature_means:      List[float]        # 8-dim
    selected_features:  List[str]          # e.g. ["dwell_norm","jitter_norm",...]
    ema_profile:        Optional[List[float]] = None   # 8-dim EMA
    ema_variance:       Optional[List[float]] = None   # 8-dim variance

class SessionVerifyRequest(BaseModel):
    """Extended heartbeat payload with per-user drift context."""
    session_token:      str
    user_id:            str
    latent_vector:      List[float]
    e_rec:              float = Field(..., ge=0)
    trust_score:        float = Field(..., ge=0, le=1)
    behavioral_drift:   float = 0.0
    adaptive_threshold: float = 0.18
    selected_features:  List[str] = Field(default_factory=list)
    sample_count:       int = 0
