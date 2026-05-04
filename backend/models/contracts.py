"""
pipeline/contracts.py

Typed contracts for every inter-stage boundary.
A single source of truth for all thresholds, enums, and dataclasses.
No business logic lives here — only shapes and constants.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


# ── Enums ─────────────────────────────────────────────────────────────────────

class Confidence(str, Enum):
    HIGH   = "high"    # ≥ threshold; agent is certain
    MEDIUM = "medium"  # uncertain; downstream may hedge
    LOW    = "low"     # guessing; fallback rules apply

class HoneypotVerdict(str, Enum):
    BOT     = "bot"      # θ < BOT_THETA_HARD
    SUSPECT = "suspect"  # BOT_THETA_HARD ≤ θ < BOT_THETA_SOFT
    HUMAN   = "human"    # θ ≥ BOT_THETA_SOFT

class SecurityPreset(str, Enum):
    ECONOMY  = "economy"   # DQN action 0 — cheapest; used for bots
    STANDARD = "standard"  # DQN action 1
    HARD     = "hard"      # DQN action 2
    PUNISHER = "punisher"  # DQN action 3 — maximum hardening

class WatchdogAction(str, Enum):
    OK                    = "ok"
    PASSIVE_REAUTH        = "passive_reauth"
    DISABLE_SENSITIVE_API = "disable_sensitive_api"
    FORCE_LOGOUT          = "force_logout"


# ── Thresholds (single source of truth) ───────────────────────────────────────

BOT_THETA_HARD   = 0.10   # θ below → definite bot → honeypot
BOT_THETA_SOFT   = 0.30   # θ below → suspect
EREC_WARN        = 0.18   # autoencoder reconstruction error → drift warning
EREC_CRITICAL    = 0.35   # → force reauth / disable APIs
TRUST_WARN       = 0.50
TRUST_CRITICAL   = 0.25
SERVER_LOAD_HIGH = 0.85


# ── Stage 1: Biometric Interpretation ─────────────────────────────────────────

@dataclass
class BiometricInput:
    """Raw signals arriving from the browser / score endpoint."""
    theta:         float           # humanity score [0, 1]  (from CNN)
    h_exp:         float           # password-entropy signal [0, 1]
    server_load:   float           # current server load [0, 1]
    user_agent:    str
    latent_vector: List[float]     # 32-dim embedding, or []
    ip_address:    str = "?"


@dataclass
class BiometricResult:
    """Stage-1 output: classified signal with confidence band."""
    theta:       float
    h_exp:       float
    server_load: float
    verdict:     HoneypotVerdict
    confidence:  Confidence
    is_bot:      bool = False
    is_suspect:  bool = False
    note:        str  = ""


# ── Stage 2: Honeypot Classification ──────────────────────────────────────────

@dataclass
class HoneypotResult:
    """Stage-2 output: routing decision + MAB arm selection."""
    should_shadow:    bool
    synthetic_token:  Optional[str]   # set iff should_shadow=True
    verdict:          HoneypotVerdict
    confidence:       Confidence
    mab_arm_selected: int             # -1 → no arm chosen (error/fallback)
    mab_confidence:   Confidence


# ── Stage 3: Resource Governor (DQN) ──────────────────────────────────────────

@dataclass
class GovernorResult:
    """Stage-3 output: Argon2id preset chosen by the DQN governor."""
    action:      int             # 0–3
    preset:      SecurityPreset
    memory_kb:   int
    time_cost:   int
    parallelism: int
    confidence:  Confidence
    fallback:    bool = False    # True when DQN was bypassed by hard override


# ── Stage 4: Session Watchdog (PPO) ───────────────────────────────────────────

@dataclass
class WatchdogResult:
    """Stage-4 output: continuous identity-drift verdict."""
    action:      WatchdogAction
    trust_score: float
    e_rec:       float           # autoencoder reconstruction error
    confidence:  Confidence
    reason:      str = ""


# ── Final Pipeline Output ──────────────────────────────────────────────────────

@dataclass
class PipelineOutput:
    """
    Returned by PipelineOrchestrator.run() and consumed directly by /score.
    Carries both the user-facing response fields and the per-stage results
    used by the admin dashboard and audit log.
    """
    # Routing
    shadow_mode:   bool
    session_token: str

    # Argon2id params chosen by the Governor
    argon2_params: dict           # {"m": int, "t": int, "p": int}
    action_label:  str

    # Biometric scores (echoed back to caller)
    humanity_score: float
    entropy_score:  float

    # Per-stage results (for logging / dashboard)
    biometric: BiometricResult
    honeypot:  HoneypotResult
    governor:  GovernorResult
    watchdog:  Optional[WatchdogResult]

    # Overall pipeline confidence (min across all stages that ran)
    pipeline_confidence: Confidence

    # Degraded flag: True if at least one stage used its fallback path
    degraded: bool = False
