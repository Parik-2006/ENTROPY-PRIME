"""
pipeline/contracts.py

Typed contracts for every inter-stage boundary.
A single source of truth for all thresholds, enums, and dataclasses.
No business logic lives here — only shapes and constants.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


# ── Enums ─────────────────────────────────────────────────────────────────────

class Confidence(str, Enum):
    HIGH   = "high"    # ≥ threshold; agent is certain
    MEDIUM = "medium"  # uncertain; downstream may hedge
    LOW    = "low"     # guessing; fallback rules apply


class HoneypotVerdict(str, Enum):
    BOT      = "bot"       # θ < BOT_THETA_HARD
    SUSPECT  = "suspect"   # BOT_THETA_HARD ≤ θ < BOT_THETA_SOFT
    HUMAN    = "human"     # θ ≥ BOT_THETA_SOFT
    LEARNING = "learning"  # user still in learning phase — observe only, never block
    CHALLENGE = "challenge" # added to support stage 2 challenge logic


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


class GovernorAction(str, Enum):
    """Behavioral response actions chosen by the PPO agent (Stage 3)."""
    ALLOW     = "allow"      # Proceed; Argon2id preset is the only hardening
    LOG       = "log"        # Allow but emit high-priority audit event
    CHALLENGE = "challenge"  # Require additional proof-of-work / CAPTCHA
    BLOCK     = "block"      # Reject request outright


# ── Thresholds (single source of truth) ───────────────────────────────────────

BOT_THETA_HARD   = 0.10   # θ below → definite bot → honeypot
BOT_THETA_SOFT   = 0.30   # θ below → suspect
EREC_WARN        = 0.18   # autoencoder reconstruction error → drift warning
EREC_CRITICAL    = 0.35   # → force reauth / disable APIs
TRUST_WARN       = 0.50
TRUST_CRITICAL   = 0.25
SERVER_LOAD_HIGH = 0.85


# ── SaaS / multi-tenant constants ─────────────────────────────────────────────

# Minimum confirmed-human samples required before a user graduates from the
# learning phase.  During the learning phase the verdict is always LEARNING
# and the pipeline never blocks the user.
LEARNING_PHASE_MIN_SAMPLES: int = 20


# ── Tenant / user identity ────────────────────────────────────────────────────

@dataclass(frozen=True)
class BiometricContext:
    """
    Identifies *who* is being evaluated and *on whose site*.

    site_id    — opaque tenant identifier (UUID or slug) issued when a
                 third-party site registers with the SaaS platform.
    user_id    — opaque end-user identifier supplied by the tenant.  The
                 platform never stores PII; the tenant is responsible for
                 mapping this to an actual user.
    session_id — optional; used for logging / replay only.
    """
    site_id:    str
    user_id:    str
    session_id: Optional[str] = None


# ── Per-user profile stored in the profile store ──────────────────────────────

@dataclass
class UserProfile:
    """
    Mutable record persisted by BiometricProfileStore, keyed by
    (site_id, user_id).

    centroid       — running mean of confirmed-human embeddings (out_dim floats).
                     None until the first human-labelled sample arrives.
    sample_count   — total samples collected (human + bot + suspect).
    human_count    — samples labelled HUMAN; used to graduate from the
                     learning phase.
    embedding_dim  — set on first write; used for shape validation on
                     subsequent writes.
    """
    site_id:       str
    user_id:       str
    centroid:      Optional[List[float]] = None
    sample_count:  int = 0
    human_count:   int = 0
    embedding_dim: Optional[int] = None

    @property
    def in_learning_phase(self) -> bool:
        """True while we haven't collected enough human samples to trust the model."""
        return self.human_count < LEARNING_PHASE_MIN_SAMPLES

    @property
    def profile_key(self) -> str:
        return f"{self.site_id}:{self.user_id}"


# ── Multi-Tenant Policy Configuration ────────────────────────────────────────

@dataclass
class TenantPolicy:
    """
    Per-tenant security policy governing Stage 3 Governor behavior.

    Loaded from the policy store (Redis/Postgres) and passed to stage3_governor.run()
    to shape both DQN (Argon2id preset) and PPO (behavioral action) decisions.

    Fields
    ──────
    site_id              — tenant identifier (opaque UUID or slug).
    risk_tolerance       — [0.0, 1.0]; 0=paranoid, 1=permissive.
                           Shapes PPO reward and hard-override thresholds.
    min_action           — floor action; PPO choice is raised to at least this.
    max_preset           — ceiling preset; DQN choice is capped at this.
    challenge_on_suspect — if True, SUSPECT verdicts always → CHALLENGE+.
    block_bots_hard      — if True, BOT verdicts always → BLOCK.
    """
    site_id:              str
    risk_tolerance:       float           = 0.5
    min_action:           Optional["GovernorAction"] = None
    max_preset:           SecurityPreset  = SecurityPreset.PUNISHER
    challenge_on_suspect: bool            = True
    block_bots_hard:      bool            = True

    def __post_init__(self):
        """Set min_action default if not provided."""
        if self.min_action is None:
            object.__setattr__(self, "min_action", GovernorAction.ALLOW)


# ── Stage 1: Biometric Interpretation ─────────────────────────────────────────

@dataclass
class BiometricInput:
    """Raw signals arriving from the browser / score endpoint (legacy path)."""
    theta:         float           # humanity score [0, 1]  (from CNN)
    h_exp:         float           # password-entropy signal [0, 1]
    server_load:   float           # current server load [0, 1]
    user_agent:    str
    latent_vector: List[float]     # 32-dim embedding, or []
    ip_address:    str = "?"


@dataclass
class ContextualBiometricInput:
    """
    Enriched Stage-1 input for the multi-tenant pipeline.

    Carries the same scalar signals as BiometricInput plus three fields
    computed by BiometricService before Stage 1 is called:

    context        — (site_id, user_id) pair that scopes this evaluation.
    learning_phase — True → classifier runs in observe-only mode; verdict
                     is always LEARNING and the pipeline never blocks.
    centroid_dist  — cosine distance between the current embedding and the
                     user's stored human centroid.  None if no centroid
                     exists yet (early learning phase).
    """
    # Original scalar signals
    theta:         float
    h_exp:         float
    server_load:   float       = 0.0
    latent_vector: List[float] = field(default_factory=list)

    # SaaS extensions (populated by BiometricService)
    context:        BiometricContext = field(
        default_factory=lambda: BiometricContext(site_id="", user_id="")
    )
    learning_phase: bool          = False
    centroid_dist:  Optional[float] = None   # None → no centroid stored yet


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

    # SaaS extensions — None on the legacy path
    context:       Optional[BiometricContext] = None
    centroid_dist: Optional[float]            = None


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


# ── Stage 3: Resource Governor (DQN + PPO) ───────────────────────────────────

@dataclass
class GovernorResult:
    """Stage-3 output: Argon2id preset (DQN) + behavioral action (PPO)."""
    action:      int                              # 0–3 (DQN)
    preset:      SecurityPreset
    memory_kb:   int
    time_cost:   int
    parallelism: int
    confidence:  Confidence
    fallback:    bool                = False      # True when DQN was bypassed
    governor_action: Optional["GovernorAction"] = None   # PPO-chosen behavioral action
    policy_applied:  str              = "__default__"  # which TenantPolicy was used


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

    # SaaS Stage 2 honeypot challenge (None unless in shadow mode)
    challenge: Optional["ChallengeConfig"] = None