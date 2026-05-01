"""
Entropy Prime — Models Package
Orchestration, ML agents, and training pipelines.
"""

# ─── Contracts & Config ───────────────────────────────────────────────────────
from .contracts import (
    BiometricInput,
    HoneypotResult,
    GovernorOutput,
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

# ─── Orchestrator ─────────────────────────────────────────────────────────────
from .orchestrator import PipelineOrchestrator

# ─── ML Agents ─────────────────────────────────────────────────────────────────
from .cnn1d import CNN1D
from .dqn import DQNAgent
from .mab import MABAgent
from .ppo import PPOAgent

# ─── Pipeline Stages ──────────────────────────────────────────────────────────
from .stage1_biometric import Stage1BiometricInterpreter
from .stage2_honeypot import Stage2HoneypotClassifier
from .stage3_governor import Stage3ResourceGovernor
from .stage4_watchdog import Stage4SessionWatchdog

# ─── Pydantic Models ──────────────────────────────────────────────────────────
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

__all__ = [
    # Contracts
    "BiometricInput",
    "HoneypotResult",
    "GovernorOutput",
    "WatchdogResult",
    "PipelineOutput",
    "Confidence",
    "HoneypotVerdict",
    "SecurityPreset",
    "WatchdogAction",
    "BOT_THETA_HARD",
    "BOT_THETA_SOFT",
    "EREC_WARN",
    "EREC_CRITICAL",
    "TRUST_WARN",
    "TRUST_CRITICAL",
    "SERVER_LOAD_HIGH",
    # Orchestrator
    "PipelineOrchestrator",
    # Agents
    "CNN1D",
    "DQNAgent",
    "MABAgent",
    "PPOAgent",
    # Stages
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
]
