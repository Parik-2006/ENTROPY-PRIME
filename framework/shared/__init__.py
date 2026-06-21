"""
framework.shared — The Contract Spine
=====================================

Single source of truth for every inter-engine boundary: enums, numeric
thresholds, dataclasses, and the onboarding state machine. Everything here is
pure data/typing with no heavy dependencies, so this module always imports
cleanly even when torch/motor/fastapi are not installed.

Facade mapping (v0.1)
---------------------
    framework.shared.*  ->  backend.models.contracts.*   (dataclasses, enums, thresholds)
    OnboardingState / ProfileBuildStatus / STABLE_SAMPLE_THRESHOLD
                        ->  backend.models.__init__       (onboarding state machine)

These re-exports are the canonical objects — not copies. Importing
``BiometricResult`` from here returns the exact same class object as importing
it from ``backend.models.contracts``.
"""
from __future__ import annotations

# ── Inter-stage contracts: dataclasses, enums, thresholds ────────────────────
from backend.models.contracts import (
    # Inputs / results
    BiometricInput,
    BiometricResult,
    HoneypotResult,
    GovernorResult,
    WatchdogResult,
    PipelineOutput,
    # SaaS / multi-tenant
    BiometricContext,
    ContextualBiometricInput,
    UserProfile,
    TenantPolicy,
    # Enums
    Confidence,
    HoneypotVerdict,
    SecurityPreset,
    WatchdogAction,
    GovernorAction,
    # Thresholds (single source of truth)
    BOT_THETA_HARD,
    BOT_THETA_SOFT,
    EREC_WARN,
    EREC_CRITICAL,
    TRUST_WARN,
    TRUST_CRITICAL,
    SERVER_LOAD_HIGH,
    LEARNING_PHASE_MIN_SAMPLES,
)

# ── Onboarding state machine (collecting -> syncing -> stable -> drifted) ─────
from backend.models import (
    OnboardingState,
    ProfileBuildStatus,
    STABLE_SAMPLE_THRESHOLD,
)

__all__ = [
    "BiometricInput",
    "BiometricResult",
    "HoneypotResult",
    "GovernorResult",
    "WatchdogResult",
    "PipelineOutput",
    "BiometricContext",
    "ContextualBiometricInput",
    "UserProfile",
    "TenantPolicy",
    "Confidence",
    "HoneypotVerdict",
    "SecurityPreset",
    "WatchdogAction",
    "GovernorAction",
    "BOT_THETA_HARD",
    "BOT_THETA_SOFT",
    "EREC_WARN",
    "EREC_CRITICAL",
    "TRUST_WARN",
    "TRUST_CRITICAL",
    "SERVER_LOAD_HIGH",
    "LEARNING_PHASE_MIN_SAMPLES",
    "OnboardingState",
    "ProfileBuildStatus",
    "STABLE_SAMPLE_THRESHOLD",
]
