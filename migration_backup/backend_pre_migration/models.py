"""
MongoDB Schemas and Pydantic Models for Entropy Prime  v2.0.0

Changes from v1.0.0
────────────────────
• Added OnboardingState enum (collecting | syncing | stable | drifted).
  Mirrors the string constants in database.py so Pydantic validators can
  check the value at the API boundary before it ever reaches MongoDB.

• BiometricProfile now carries `onboarding_state: OnboardingState` and
  exposes two computed properties:
    - drift_detection_armed  → bool  (True only when state == stable)
    - progress               → float [0, 1] clamped sample count ratio

• ProfileBuildStatus is a new lightweight response model returned by
  GET /biometric/profile/{user_id}/status and included in every sync
  response so the frontend state machine always has a single authoritative
  source of truth for which panel to render.

• BiometricProfileUpdateRequest now includes onboarding_state so the
  backend sync endpoint can accept a forced transition from the client
  (e.g. the client signalling that it has crossed the sample threshold
  and persisted its EMA, so the backend should commit `stable`).

• All pre-existing models are preserved and signature-compatible.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from bson import ObjectId
from pydantic import BaseModel, Field, EmailStr, computed_field


# ─────────────────────────────────────────────────────────────────────────────
# Onboarding state machine
# ─────────────────────────────────────────────────────────────────────────────

class OnboardingState(str, Enum):
    """
    Lifecycle of a user's biometric profile.

    collecting  — Fewer than STABLE_SAMPLE_THRESHOLD samples have been
                  aggregated. Drift detection is suppressed; the UI shows
                  the collection progress bar.

    syncing     — The client has crossed the sample threshold and has sent
                  a sync payload, but the backend has not yet confirmed the
                  write.  Treated identically to `collecting` by the drift
                  gate, but distinct so the UI can show a "saving…" state
                  rather than the progress bar.

    stable      — The profile has enough samples for drift detection to be
                  meaningful. The watchdog heartbeat is now fully armed.

    drifted     — The watchdog detected a significant departure from the EMA
                  baseline while the profile was `stable`. The session is
                  flagged for re-authentication. Only an explicit reset (via
                  POST /biometric/profile/reset) or a completed re-auth
                  transitions back to `collecting`.
    """
    COLLECTING = "collecting"
    SYNCING    = "syncing"
    STABLE     = "stable"
    DRIFTED    = "drifted"


# ─────────────────────────────────────────────────────────────────────────────
# Feature names (must stay in sync with biometrics.js FEATURE_NAMES)
# ─────────────────────────────────────────────────────────────────────────────

FEATURE_NAMES: List[str] = [
    "dwell_norm",
    "flight_norm",
    "speed_norm",
    "jitter_norm",
    "accel_norm",
    "rhythm_norm",
    "pause_norm",
    "bigram_norm",
]

# Minimum samples before the profile is considered stable.
# Imported from database.py at runtime to keep a single source of truth;
# re-declared here so models.py can be imported independently in tests.
STABLE_SAMPLE_THRESHOLD = 50


# ─────────────────────────────────────────────────────────────────────────────
# SaaS & Multi-Tenant Models  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class Tenant(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    name: str
    admin_email: EmailStr
    subscription_tier: str = "free"  # free, pro, enterprise
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class Site(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    tenant_id: str
    site_name: str
    domain: str
    key_digest: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# ─────────────────────────────────────────────────────────────────────────────
# User Models  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    plain_password: str

    model_config = {
        "json_schema_extra": {
            "example": {"email": "user@example.com", "plain_password": "securepassword123"}
        }
    }


class UserLogin(BaseModel):
    email: EmailStr
    plain_password: str


class User(BaseModel):
    id: Optional[str]  = Field(default=None, alias="_id")
    tenant_id: Optional[str] = None
    email: str
    password_hash: str
    created_at: datetime  = Field(default_factory=datetime.utcnow)
    updated_at: datetime  = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    is_active: bool = True
    security_level: str = "standard"

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class UserResponse(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    email: str
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime]
    is_active: bool
    security_level: str

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# ─────────────────────────────────────────────────────────────────────────────
# Session Models  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class Session(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    tenant_id: Optional[str] = None
    site_id: Optional[str] = None
    user_id: str
    session_token: str
    latent_vector: List[float] = Field(default_factory=lambda: [0.0] * 32)
    created_at: datetime  = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    last_verified: Optional[datetime] = None
    trust_score: float = 1.0
    is_active: bool = True

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# ─────────────────────────────────────────────────────────────────────────────
# Per-User Biometric Profile Models  (updated)
# ─────────────────────────────────────────────────────────────────────────────

class BiometricSample(BaseModel):
    """
    Single 8-channel biometric observation.

    Raw keystrokes and mouse coordinates are NEVER included here.
    Only derived metrics (dwell time, flight time, etc.) are stored.
    """
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
    m2s:      List[float] = Field(default_factory=lambda: [0.1] * 8)
    n:        int          = 0
    selected: List[int]   = Field(default_factory=lambda: list(range(8)))
    k:        int          = 6

    def selected_feature_names(self) -> List[str]:
        return [FEATURE_NAMES[i] for i in self.selected if i < len(FEATURE_NAMES)]


class BehavioralProfileState(BaseModel):
    """
    Per-user EMA behavioral profile.
    Tracks the user's stable behavioral pattern and detects drift.
    """
    ema_profile:   Optional[List[float]] = None
    ema_variance:  Optional[List[float]] = None
    sample_count:  int   = 0
    drift_history: List[float] = Field(default_factory=list)
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

    onboarding_state drives both the frontend state machine and the
    server-side drift-detection gate.  Drift is only computed when
    the state is `stable`; all other states suppress it to prevent
    false positives during the cold-start period.
    """
    id: Optional[str] = Field(default=None, alias="_id")
    tenant_id: Optional[str] = None
    site_id:   Optional[str] = None
    user_id:   str

    # State machine field — the single source of truth for which
    # UI panel to render and whether drift detection is armed.
    onboarding_state: OnboardingState = OnboardingState.COLLECTING

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

    # Summary stats (updated on each sync from the client)
    sample_count:       int   = 0
    last_drift:         float = 0.0
    adaptive_threshold: float = 1.8
    selected_features:  List[str]   = Field(default_factory=list)
    feature_means:      List[float] = Field(default_factory=lambda: [0.5] * 8)
    ema_profile:        Optional[List[float]] = None
    ema_variance:       Optional[List[float]] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    reset_at:   Optional[datetime] = None

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    @property
    def drift_detection_armed(self) -> bool:
        """
        True only when the profile is in the `stable` state.
        The watchdog heartbeat should skip drift computation for all
        other states to avoid false positives on cold-start profiles.
        """
        return self.onboarding_state == OnboardingState.STABLE

    @property
    def progress(self) -> float:
        """Clamped [0, 1] fraction of the required sample count."""
        return min(self.sample_count / STABLE_SAMPLE_THRESHOLD, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Profile Build Status — lightweight response model
# ─────────────────────────────────────────────────────────────────────────────

class ProfileBuildStatus(BaseModel):
    """
    Returned by GET /biometric/profile/{user_id}/status and embedded in
    every sync response.  Gives the frontend a single authoritative
    source of truth for its state machine without returning the full
    profile document.
    """
    user_id:            str
    tenant_id:          Optional[str]
    onboarding_state:   OnboardingState
    sample_count:       int
    progress:           float           = Field(ge=0.0, le=1.0)
    drift_detection_armed: bool
    last_drift:         float
    adaptive_threshold: float
    selected_features:  List[str]
    updated_at:         Optional[datetime]

    @classmethod
    def from_profile(cls, profile: dict) -> "ProfileBuildStatus":
        """Construct from a raw MongoDB document (ObjectIds already stringified)."""
        sample_count = profile.get("sample_count", 0)
        state_raw    = profile.get("onboarding_state", OnboardingState.COLLECTING.value)
        try:
            state = OnboardingState(state_raw)
        except ValueError:
            state = OnboardingState.COLLECTING

        return cls(
            user_id               = profile.get("user_id", ""),
            tenant_id             = profile.get("tenant_id"),
            onboarding_state      = state,
            sample_count          = sample_count,
            progress              = min(sample_count / STABLE_SAMPLE_THRESHOLD, 1.0),
            drift_detection_armed = state == OnboardingState.STABLE,
            last_drift            = profile.get("last_drift", 0.0),
            adaptive_threshold    = profile.get("adaptive_threshold", 1.8),
            selected_features     = profile.get("selected_features", []),
            updated_at            = profile.get("updated_at"),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Drift Event Model  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class DriftEvent(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    tenant_id: Optional[str] = None
    site_id:   Optional[str] = None
    user_id:   str
    timestamp:          datetime = Field(default_factory=datetime.utcnow)
    drift_score:        float
    adaptive_threshold: float
    trust_score:        float
    e_rec:              float
    selected_features:  List[str]
    action:             str
    session_token:      str = ""

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class DriftSummary(BaseModel):
    user_id:      str
    total_events: int
    avg_drift:    float
    max_drift:    float
    avg_trust:    float
    last_event:   Optional[datetime]


# ─────────────────────────────────────────────────────────────────────────────
# Feature Selection History Model  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class FeatureSelectionSnapshot(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id:           str
    recorded_at:       datetime = Field(default_factory=datetime.utcnow)
    selected_features: List[str]
    feature_means:     List[float]
    feature_variances: List[float]
    sample_count:      int

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# ─────────────────────────────────────────────────────────────────────────────
# Honeypot Model  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class HoneypotEntry(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    tenant_id: Optional[str] = None
    site_id:   Optional[str] = None
    timestamp:  datetime = Field(default_factory=datetime.utcnow)
    user_agent: str
    theta:      float
    ip_address: str
    path:       str = "/"
    headers:    dict = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
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
    """
    Payload from the browser biometric sync (POST /biometric/profile).

    `onboarding_state` is optional; the client may supply it when it knows it
    has crossed the stable threshold.  The server validates the transition and
    ignores invalid state jumps (e.g. collecting → drifted is not allowed
    from the client side).

    Raw keystroke / mouse data must never appear in this payload.
    Only aggregated statistics (means, EMA vectors, counts) are accepted.
    """
    user_id:            str
    sample_count:       int
    last_drift:         float
    adaptive_threshold: float
    feature_means:      List[float]         = Field(default_factory=list)
    selected_features:  List[str]           = Field(default_factory=list)
    ema_profile:        Optional[List[float]] = None
    ema_variance:       Optional[List[float]] = None
    # Client may request a state transition to `stable` once it has
    # persisted its local EMA.  Other transitions are ignored server-side.
    onboarding_state:   Optional[OnboardingState] = None


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
    # Heartbeat must declare the profile state so the server can suppress
    # drift detection for users who haven't finished onboarding.
    onboarding_state:   OnboardingState = OnboardingState.COLLECTING