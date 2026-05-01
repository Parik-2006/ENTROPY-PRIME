"""
Entropy Prime — Multi-Agent Pipeline Contracts
All inter-model I/O is typed here. Every agent consumes and produces
one of these dataclasses. Nothing raw passes between stages.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── Enums ─────────────────────────────────────────────────────────────────────

class Confidence(str, Enum):
    HIGH   = "high"    # agent is certain (score ≥ threshold)
    MEDIUM = "medium"  # agent is uncertain; downstream may hedge
    LOW    = "low"     # agent is guessing; fallback rules apply

class HoneypotVerdict(str, Enum):
    BOT      = "bot"       # θ < BOT_THETA_HARD
    SUSPECT  = "suspect"   # BOT_THETA_HARD ≤ θ < BOT_THETA_SOFT
    HUMAN    = "human"     # θ ≥ BOT_THETA_SOFT

class SecurityPreset(str, Enum):
    ECONOMY  = "economy"   # DQN action 0
    STANDARD = "standard"  # DQN action 1
    HARD     = "hard"      # DQN action 2
    PUNISHER = "punisher"  # DQN action 3

class WatchdogAction(str, Enum):
    OK                    = "ok"
    PASSIVE_REAUTH        = "passive_reauth"
    DISABLE_SENSITIVE_API = "disable_sensitive_apis"
    FORCE_LOGOUT          = "force_logout"


# ── Thresholds (single source of truth) ───────────────────────────────────────

BOT_THETA_HARD    = 0.10   # below → definite bot → honeypot
BOT_THETA_SOFT    = 0.30   # below → suspect
EREC_WARN         = 0.18   # autoencoder reconstruction error → drift warning
EREC_CRITICAL     = 0.35   # → force reauth / disable APIs
TRUST_WARN        = 0.50
TRUST_CRITICAL    = 0.25
SERVER_LOAD_HIGH  = 0.85


# ── Stage 1: Biometric Interpretation ─────────────────────────────────────────

@dataclass
class BiometricInput:
    """Raw signals arriving from the browser."""
    theta:          float          # humanity score [0,1]  (from CNN)
    h_exp:          float          # password entropy [0,1]
    server_load:    float          # [0,1]
    user_agent:     str
    latent_vector:  list[float]    # 32-dim or []
    ip_address:     str = "?"

@dataclass
class BiometricResult:
    """Stage-1 output: classified signal with confidence."""
    theta:       float
    h_exp:       float
    server_load: float
    verdict:     HoneypotVerdict
    confidence:  Confidence
    # Derived signals for downstream agents
    is_bot:      bool = False
    is_suspect:  bool = False
    note:        str  = ""


# ── Stage 2: Honeypot Classification ──────────────────────────────────────────

@dataclass
class HoneypotResult:
    """Stage-2 output: routing decision."""
    should_shadow:    bool
    synthetic_token:  Optional[str]   # set only when should_shadow=True
    verdict:          HoneypotVerdict
    confidence:       Confidence
    mab_arm_selected: int             # which deception strategy was chosen
    mab_confidence:   Confidence


# ── Stage 3: Resource Governor (DQN) ──────────────────────────────────────────

@dataclass
class GovernorResult:
    """Stage-3 output: Argon2id hardening decision."""
    action:      int             # 0-3
    preset:      SecurityPreset
    memory_kb:   int
    time_cost:   int
    parallelism: int
    confidence:  Confidence
    fallback:    bool = False    # True when DQN was bypassed


# ── Stage 4: Session Watchdog (PPO) ───────────────────────────────────────────

@dataclass
class WatchdogResult:
    """Stage-4 output: continuous identity verification."""
    action:      WatchdogAction
    trust_score: float
    e_rec:       float
    confidence:  Confidence
    reason:      str = ""


# ── Final Policy Output ────────────────────────────────────────────────────────

@dataclass
class PipelineOutput:
    """
    What /score returns after all four agents have run.
    Frontend consumes this directly.
    """
    # Routing
    shadow_mode:      bool
    session_token:    str

    # Argon2id params chosen by Governor
    argon2_params:    dict           # {m, t, p}
    action_label:     str

    # Scores
    humanity_score:   float
    entropy_score:    float

    # Per-stage results (for logging / admin dashboard)
    biometric:        BiometricResult
    honeypot:         HoneypotResult
    governor:         GovernorResult
    watchdog:         Optional[WatchdogResult]

    # Overall confidence of the pipeline run
    pipeline_confidence: Confidence

    # Degraded-mode flag: at least one agent used its fallback
    degraded:         bool = False
