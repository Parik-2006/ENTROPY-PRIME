"""
Entropy Prime — Models Package
Contracts, orchestration, ML agents, and training pipelines.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# ─── Contracts & Config ───────────────────────────────────────────────────────
from .contracts import (
    BiometricInput,
    BiometricResult,
    HoneypotResult,
    GovernorResult,
    WatchdogResult,
    PipelineOutput,
    Confidence,
    HoneypotVerdict,
    SecurityPreset,
    WatchdogAction,
    BOT_THETA_HARD,
    BOT_THETA_SOFT,
    EREC_WARN,
    EREC_CRITICAL,
    TRUST_WARN,
    TRUST_CRITICAL,
    SERVER_LOAD_HIGH,
)

# ─── Lazy Imports: Torch/ML Dependencies ──────────────────────────────────────
try:
    from .orchestrator import PipelineOrchestrator
    from .cnn1d import CNN1D
    from .dqn import DQNAgent
    from .mab import MABAgent
    from .ppo import PPOAgent
    from .stage1_biometric import Stage1BiometricInterpreter
    from .stage2_honeypot import Stage2HoneypotClassifier
    from .stage3_governor import Stage3ResourceGovernor
    from .stage4_watchdog import Stage4SessionWatchdog
    _TORCH_AVAILABLE = True
except ImportError as e:
    # PyTorch or related dependency not available; stages will be imported later
    _TORCH_AVAILABLE = False
    _TORCH_ERROR = str(e)

# ─── Pydantic Models ──────────────────────────────────────────────────────────
try:
    from .pydantic_models import (
        UserCreate,
        UserLogin,
        User,
        UserResponse,
        Session,
        BiometricSample,
        BiometricProfile,
        HoneypotEntry,
        AuthResponse,
        PasswordHashResponse,
    )
except ImportError:
    pass


# ─── Onboarding State Machine ────────────────────────────────────────────────

class OnboardingState(str, Enum):
    COLLECTING = "collecting"
    SYNCING = "syncing"
    STABLE = "stable"
    DRIFTED = "drifted"


STABLE_SAMPLE_THRESHOLD = 50


class ProfileBuildStatus(BaseModel):
    user_id: str
    tenant_id: Optional[str] = None
    onboarding_state: OnboardingState = OnboardingState.COLLECTING
    sample_count: int = 0
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    drift_detection_armed: bool = False
    last_drift: float = 0.0
    adaptive_threshold: float = 1.8
    selected_features: list[str] = Field(default_factory=list)
    updated_at: Optional[datetime] = None

    @classmethod
    def from_profile(cls, profile: dict) -> "ProfileBuildStatus":
        state_raw = profile.get("onboarding_state", OnboardingState.COLLECTING.value)
        try:
            state = OnboardingState(state_raw)
        except ValueError:
            state = OnboardingState.COLLECTING

        sample_count = int(profile.get("sample_count", 0) or 0)
        return cls(
            user_id=profile.get("user_id", ""),
            tenant_id=profile.get("tenant_id"),
            onboarding_state=state,
            sample_count=sample_count,
            progress=min(sample_count / STABLE_SAMPLE_THRESHOLD, 1.0),
            drift_detection_armed=state == OnboardingState.STABLE,
            last_drift=float(profile.get("last_drift", 0.0) or 0.0),
            adaptive_threshold=float(profile.get("adaptive_threshold", 1.8) or 1.8),
            selected_features=list(profile.get("selected_features", []) or []),
            updated_at=profile.get("updated_at"),
        )

__all__ = [
    # Contracts
    "BiometricInput",
    "BiometricResult",
    "HoneypotResult",
    "GovernorResult",
    "WatchdogResult",
    "PipelineOutput",
    # Enums
    "Confidence",
    "HoneypotVerdict",
    "SecurityPreset",
    "WatchdogAction",
    # Thresholds
    "BOT_THETA_HARD",
    "BOT_THETA_SOFT",
    "EREC_WARN",
    "EREC_CRITICAL",
    "TRUST_WARN",
    "TRUST_CRITICAL",
    "SERVER_LOAD_HIGH",
    # Orchestrator & Agents (if available)
    "PipelineOrchestrator",
    "CNN1D",
    "DQNAgent",
    "MABAgent",
    "PPOAgent",
    # Stages (if available)
    "Stage1BiometricInterpreter",
    "Stage2HoneypotClassifier",
    "Stage3ResourceGovernor",
    "Stage4SessionWatchdog",
    # Pydantic Models
    "UserCreate",
    "UserLogin",
    "User",
    "UserResponse",
    "Session",
    "BiometricSample",
    "BiometricProfile",
    "HoneypotEntry",
    "AuthResponse",
    "PasswordHashResponse",
    # Onboarding state machine
    "OnboardingState",
    "ProfileBuildStatus",
    "STABLE_SAMPLE_THRESHOLD",
    # Diagnostics
    "_TORCH_AVAILABLE",
]
