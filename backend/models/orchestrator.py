"""
pipeline/orchestrator.py  —  Pipeline Orchestrator

Sequences Stages 1-4 with explicit I/O contracts, confidence propagation,
and degraded-mode tracking.  This is the single entry point for /score.

Design notes
────────────
• Stateless: holds model references only.  Each call to run() is safe for
  concurrent requests without any locking.
• Fail-safe: every stage is wrapped in try/except.  Failures produce fallback
  results and set degraded=True, never 500s.
• Bot short-circuit: confirmed bots skip Stages 3 and 4 entirely — no point
  profiling a known attacker.
• Confidence roll-up: overall pipeline confidence is the minimum across all
  stages that ran.  A single LOW stage poisons the rating (conservative).
"""
from __future__ import annotations

import hashlib
import hmac as hmac_mod   # aliased to avoid shadowing the local `hmac` name
import logging
import secrets
import time
from typing import Optional

from .contracts import (
    BiometricInput,
    BiometricResult,
    Confidence,
    GovernorResult,
    HoneypotResult,
    HoneypotVerdict,
    PipelineOutput,
    SecurityPreset,
    WatchdogAction,
    WatchdogResult,
)
from . import stage1_biometric as s1
from . import stage2_honeypot  as s2
from . import stage3_governor  as s3
from . import stage4_watchdog  as s4

logger = logging.getLogger("entropy_prime.pipeline")


class PipelineOrchestrator:
    """
    Stateless orchestrator — holds references to model agents only.

    Dependency injection via constructor lets unit tests pass in mock agents
    without touching global state.
    """

    def __init__(
        self,
        dqn_agent,
        mab_agent,
        ppo_agent,
        shadow_secret:  str,
        session_secret: str,
    ):
        self._dqn    = dqn_agent
        self._mab    = mab_agent
        self._ppo    = ppo_agent
        self._shadow = shadow_secret
        self._sess   = session_secret
 
    @property
    def dqn(self): return self._dqn
 
    @property
    def mab(self): return self._mab
 
    @property
    def ppo(self): return self._ppo
 
    @ppo.setter
    def ppo(self, val): self._ppo = val


    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, raw: BiometricInput) -> PipelineOutput:
        """
        Full 4-stage pipeline.  Always returns a PipelineOutput — never raises.

        Stage order:
          S1 Biometric → S2 Honeypot → [short-circuit if bot]
          → S3 Governor → S4 Watchdog
        """
        degraded = False

        # ── Stage 1: Biometric Interpretation ─────────────────────────────────
        # Failure here is serious — fall back to HUMAN/LOW so real users are
        # never locked out by an instrumentation error.
        try:
            bio = s1.run(raw)
            logger.debug("[S1] verdict=%s conf=%s θ=%.3f", bio.verdict, bio.confidence, bio.theta)
        except Exception as exc:
            logger.error("[S1] FAILED: %s — safe defaults applied", exc)
            bio      = _safe_bio(raw)
            degraded = True

        # ── Stage 2: Honeypot Classification ──────────────────────────────────
        # Low MAB confidence (cold-start) sets degraded but does NOT abort.
        try:
            honeypot = s2.run(bio, self._mab, self._shadow, raw.ip_address)
            if honeypot.mab_confidence == Confidence.LOW:
                degraded = True
            logger.debug("[S2] shadow=%s arm=%d mab_conf=%s",
                         honeypot.should_shadow, honeypot.mab_arm_selected,
                         honeypot.mab_confidence)
        except Exception as exc:
            logger.error("[S2] FAILED: %s — no shadow routing", exc)
            honeypot = _safe_honeypot(bio)
            degraded = True

        # ── Bot short-circuit ──────────────────────────────────────────────────
        # Bots get ECONOMY (cheapest hashing) — no point profiling them further.
        if honeypot.should_shadow:
            gov   = _economy_governor()
            token = honeypot.synthetic_token or _make_session_token(
                uid    = "bot_" + secrets.token_hex(6),
                lv     = raw.latent_vector,
                secret = self._sess,
            )
            logger.info("[PIPELINE] Bot short-circuit — shadow=True arm=%d",
                        honeypot.mab_arm_selected)
            return _assemble(raw, bio, honeypot, gov, None, token, degraded)

        # ── Stage 3: Resource Governor (DQN) ──────────────────────────────────
        try:
            gov = s3.run(bio, self._dqn)
            if gov.fallback:
                degraded = True
            logger.debug("[S3] preset=%s conf=%s fallback=%s",
                         gov.preset, gov.confidence, gov.fallback)
        except Exception as exc:
            logger.error("[S3] FAILED: %s — STANDARD preset", exc)
            gov      = _safe_governor()
            degraded = True

        # ── Stage 4: Session Watchdog (PPO) ───────────────────────────────────
        # Optional: only runs when a 32-dim latent vector is present.
        # Non-fatal: failure sets degraded=True but does not abort.
        watchdog: Optional[WatchdogResult] = None
        try:
            if raw.latent_vector and len(raw.latent_vector) == 32:
                watchdog = s4.run(
                    latent_vector = raw.latent_vector,
                    e_rec         = 0.0,   # baseline on first contact
                    trust_score   = 1.0,   # new session starts fully trusted
                    ppo_agent     = self._ppo,
                )
                logger.debug("[S4] action=%s trust=%.3f e_rec=%.3f conf=%s",
                             watchdog.action, watchdog.trust_score,
                             watchdog.e_rec, watchdog.confidence)
        except Exception as exc:
            logger.warning("[S4] FAILED (non-critical): %s", exc)
            degraded = True

        # ── Token ──────────────────────────────────────────────────────────────
        uid   = "usr_" + secrets.token_hex(6)
        token = _make_session_token(uid, raw.latent_vector, self._sess)

        return _assemble(raw, bio, honeypot, gov, watchdog, token, degraded)

    # ── Standalone watchdog (heartbeat endpoint) ──────────────────────────────

    def run_watchdog(
        self,
        latent_vector: list[float],
        e_rec:         float,
        trust_score:   float,
    ) -> WatchdogResult:
        """
        Standalone watchdog call used by the /session/verify heartbeat.
        Always returns a WatchdogResult (never raises).
        """
        try:
            return s4.run(latent_vector, e_rec, trust_score, self._ppo)
        except Exception as exc:
            logger.error("[S4-standalone] FAILED: %s", exc)
            action, conf, reason = s4._fallback_rules(e_rec, trust_score)
            return WatchdogResult(
                action      = action,
                trust_score = trust_score,
                e_rec       = e_rec,
                confidence  = conf,
                reason      = f"error_fallback: {reason}",
            )

    # ── MAB feedback ──────────────────────────────────────────────────────────

    def report_mab_reward(self, arm: int, reward: float) -> None:
        """Feedback from shadow sessions back to the MAB agent."""
        s2.update_mab_reward(self._mab, arm, reward)


# ── Fallback constructors ──────────────────────────────────────────────────────

def _safe_bio(raw: BiometricInput) -> BiometricResult:
    return BiometricResult(
        theta       = 0.5,
        h_exp       = raw.h_exp,
        server_load = raw.server_load,
        verdict     = HoneypotVerdict.HUMAN,
        confidence  = Confidence.LOW,
        is_bot      = False,
        is_suspect  = False,
        note        = "stage1_error_fallback",
    )


def _safe_honeypot(bio: BiometricResult) -> HoneypotResult:
    """No shadow routing — benefit of the doubt to the user."""
    return HoneypotResult(
        should_shadow    = False,
        synthetic_token  = None,
        verdict          = bio.verdict,
        confidence       = Confidence.LOW,
        mab_arm_selected = -1,
        mab_confidence   = Confidence.LOW,
    )


def _safe_governor() -> GovernorResult:
    return GovernorResult(
        action      = 1,
        preset      = SecurityPreset.STANDARD,
        memory_kb   = 131_072,
        time_cost   = 3,
        parallelism = 4,
        confidence  = Confidence.LOW,
        fallback    = True,
    )


def _economy_governor() -> GovernorResult:
    return GovernorResult(
        action      = 0,
        preset      = SecurityPreset.ECONOMY,
        memory_kb   = 65_536,
        time_cost   = 2,
        parallelism = 4,
        confidence  = Confidence.HIGH,
        fallback    = True,
    )


# ── Confidence roll-up ────────────────────────────────────────────────────────

_CONF_RANK = {Confidence.HIGH: 2, Confidence.MEDIUM: 1, Confidence.LOW: 0}


def _min_confidence(*confs: Confidence) -> Confidence:
    """Lowest confidence wins — a single LOW stage poisons the pipeline rating."""
    return min(confs, key=lambda c: _CONF_RANK[c])


# ── Token helper ──────────────────────────────────────────────────────────────

def _make_session_token(uid: str, lv: list[float], secret: str) -> str:
    """
    Tamper-evident session token.

    Format (after the random URL-safe prefix):
        <8-char prefix>.<hex(uid:ts:latent_hash16:hmac_hex)>

    The HMAC ties every token to a specific (uid, timestamp, latent snapshot)
    tuple.  Server-side verification must recompute the HMAC before trusting
    any field extracted from the token.
    """
    latent_hash = hashlib.sha256(str(lv).encode()).hexdigest()[:16]
    payload     = f"{uid}:{int(time.time())}:{latent_hash}"
    sig         = hmac_mod.new(
        secret.encode(), payload.encode(), hashlib.sha256,
    ).hexdigest()
    encoded = (payload + ":" + sig).encode().hex()
    return secrets.token_urlsafe(8) + "." + encoded


# ── Assemble PipelineOutput ───────────────────────────────────────────────────

def _assemble(
    raw:      BiometricInput,
    bio:      BiometricResult,
    honeypot: HoneypotResult,
    gov:      GovernorResult,
    watchdog: Optional[WatchdogResult],
    token:    str,
    degraded: bool,
) -> PipelineOutput:
    confs: list[Confidence] = [bio.confidence, honeypot.confidence, gov.confidence]
    if watchdog is not None:
        confs.append(watchdog.confidence)
    overall = _min_confidence(*confs)

    return PipelineOutput(
        shadow_mode         = honeypot.should_shadow,
        session_token       = token,
        argon2_params       = {
            "m": gov.memory_kb,
            "t": gov.time_cost,
            "p": gov.parallelism,
        },
        action_label        = gov.preset.value,
        humanity_score      = bio.theta,
        entropy_score       = bio.h_exp,
        biometric           = bio,
        honeypot            = honeypot,
        governor            = gov,
        watchdog            = watchdog,
        pipeline_confidence = overall,
        degraded            = degraded,
    )
