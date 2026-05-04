"""
Entropy Prime — Models Package
Contracts, orchestration, ML agents, and training pipelines.
"""

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
    # Diagnostics
    "_TORCH_AVAILABLE",
]
