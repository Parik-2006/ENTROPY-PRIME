"""
Entropy Prime — Pipeline Orchestrator
Sequences stages 1-4 with explicit I/O contracts, confidence propagation,
and degraded-mode tracking. This is the single entry point for /score.

Usage:
    from pipeline.orchestrator import PipelineOrchestrator
    orch = PipelineOrchestrator(dqn, mab, ppo, shadow_secret)
    output: PipelineOutput = await orch.run(raw_input, session_token)
"""
from __future__ import annotations

import hashlib, hmac, logging, secrets, time
from typing import Optional

from .contracts import (
    BiometricInput, PipelineOutput,
    Confidence, WatchdogResult,
)
from . import stage1_biometric as s1
from . import stage2_honeypot  as s2
from . import stage3_governor  as s3
from . import stage4_watchdog  as s4

logger = logging.getLogger("entropy_prime.pipeline")


class PipelineOrchestrator:
    """
    Stateless orchestrator — holds references to model agents only.
    Each call to `run()` is fully independent (safe for concurrent requests).

    Degraded mode: if any stage uses its fallback, the final PipelineOutput
    carries degraded=True so ops dashboards can alert.
    """

    def __init__(
        self,
        dqn_agent,
        mab_agent,
        ppo_agent,
        shadow_secret: str,
        session_secret: str,
    ):
        self._dqn    = dqn_agent
        self._mab    = mab_agent
        self._ppo    = ppo_agent
        self._shadow = shadow_secret
        self._sess   = session_secret

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, raw: BiometricInput) -> PipelineOutput:
        """
        Full 4-stage pipeline. Always returns a PipelineOutput — never raises.
        Errors within a stage are caught and converted to fallback results.
        """
        degraded = False

        # ── Stage 1: Biometric interpretation ────────────────────────────────
        try:
            bio = s1.run(raw)
            logger.debug("[S1] verdict=%s conf=%s θ=%.3f",
                         bio.verdict, bio.confidence, bio.theta)
        except Exception as exc:
            logger.error("[S1] FAILED: %s — using safe defaults", exc)
            bio      = _safe_bio(raw)
            degraded = True

        # ── Stage 2: Honeypot classification ─────────────────────────────────
        try:
            honeypot = s2.run(bio, self._mab, self._shadow, raw.ip_address)
            if honeypot.mab_confidence == Confidence.LOW:
                degraded = True
            logger.debug("[S2] shadow=%s arm=%d mab_conf=%s",
                         honeypot.should_shadow, honeypot.mab_arm_selected,
                         honeypot.mab_confidence)
        except Exception as exc:
            logger.error("[S2] FAILED: %s — no shadow routing", exc)
            honeypot = _safe_honeypot(bio, self._shadow, raw.ip_address)
            degraded = True

        # ── If bot → short-circuit: no need to run Governor / Watchdog ───────
        if honeypot.should_shadow:
            gov = _economy_governor()          # minimal resource use for bots
            return _assemble(
                raw, bio, honeypot, gov, watchdog=None,
                token=honeypot.synthetic_token,
                degraded=degraded,
            )

        # ── Stage 3: Resource Governor (DQN) ─────────────────────────────────
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

        # ── Stage 4: Session Watchdog (PPO) — optional, non-blocking ─────────
        watchdog: Optional[WatchdogResult] = None
        try:
            if raw.latent_vector and len(raw.latent_vector) == 32:
                watchdog = s4.run(
                    latent_vector = raw.latent_vector,
                    e_rec         = 0.0,   # baseline on first contact
                    trust_score   = 1.0,
                    ppo_agent     = self._ppo,
                )
                logger.debug("[S4] action=%s conf=%s", watchdog.action, watchdog.confidence)
        except Exception as exc:
            logger.warning("[S4] FAILED (non-critical): %s", exc)
            degraded = True

        # ── Token ─────────────────────────────────────────────────────────────
        uid   = "usr_" + secrets.token_hex(6)
        token = _make_session_token(uid, raw.latent_vector, self._sess)

        return _assemble(raw, bio, honeypot, gov, watchdog, token, degraded)

    def run_watchdog(
        self,
        latent_vector: list[float],
        e_rec:         float,
        trust_score:   float,
    ) -> WatchdogResult:
        """
        Standalone watchdog call used by the /session/verify heartbeat endpoint.
        Always returns a WatchdogResult (never raises).
        """
        try:
            return s4.run(latent_vector, e_rec, trust_score, self._ppo)
        except Exception as exc:
            logger.error("[S4-standalone] FAILED: %s", exc)
            from .contracts import WatchdogAction
            from . import stage4_watchdog
            action, conf, reason = stage4_watchdog._fallback_rules(e_rec, trust_score)
            return WatchdogResult(
                action      = action,
                trust_score = trust_score,
                e_rec       = e_rec,
                confidence  = conf,
                reason      = f"error_fallback: {reason}",
            )

    def report_mab_reward(self, arm: int, reward: float) -> None:
        """Feedback from shadow sessions back to the MAB agent."""
        s2.update_mab_reward(self._mab, arm, reward)


# ── Fallback constructors ──────────────────────────────────────────────────────

def _safe_bio(raw: BiometricInput):
    from .contracts import BiometricResult, HoneypotVerdict, Confidence
    return BiometricResult(
        theta=0.5, h_exp=raw.h_exp, server_load=raw.server_load,
        verdict=HoneypotVerdict.HUMAN, confidence=Confidence.LOW,
        is_bot=False, is_suspect=False, note="stage1_error_fallback",
    )

def _safe_honeypot(bio, shadow_secret, ip):
    from .contracts import HoneypotResult, Confidence
    return HoneypotResult(
        should_shadow=False, synthetic_token=None,
        verdict=bio.verdict, confidence=Confidence.LOW,
        mab_arm_selected=-1, mab_confidence=Confidence.LOW,
    )

def _safe_governor():
    from .contracts import GovernorResult, SecurityPreset, Confidence
    return GovernorResult(
        action=1, preset=SecurityPreset.STANDARD,
        memory_kb=131_072, time_cost=3, parallelism=4,
        confidence=Confidence.LOW, fallback=True,
    )

def _economy_governor():
    from .contracts import GovernorResult, SecurityPreset, Confidence
    return GovernorResult(
        action=0, preset=SecurityPreset.ECONOMY,
        memory_kb=65_536, time_cost=2, parallelism=4,
        confidence=Confidence.HIGH, fallback=True,
    )


# ── Pipeline confidence roll-up ────────────────────────────────────────────────

_CONF_RANK = {Confidence.HIGH: 2, Confidence.MEDIUM: 1, Confidence.LOW: 0}

def _min_confidence(*confs: Confidence) -> Confidence:
    return min(confs, key=lambda c: _CONF_RANK[c])


# ── Token helper ───────────────────────────────────────────────────────────────

def _make_session_token(uid: str, lv: list, secret: str) -> str:
    vh  = hashlib.sha256(str(lv).encode()).hexdigest()[:16]
    pay = f"{uid}:{time.time():.0f}:{vh}"
    sig = hmac.new(secret.encode(), pay.encode(), hashlib.sha256).hexdigest()
    return secrets.token_urlsafe(8) + "." + (pay + ":" + sig).encode().hex()


# ── Assemble final output ──────────────────────────────────────────────────────

def _assemble(raw, bio, honeypot, gov, watchdog, token, degraded) -> PipelineOutput:
    confs = [bio.confidence, honeypot.confidence, gov.confidence]
    if watchdog:
        confs.append(watchdog.confidence)
    overall = _min_confidence(*confs)

    return PipelineOutput(
        shadow_mode      = honeypot.should_shadow,
        session_token    = token,
        argon2_params    = {"m": gov.memory_kb, "t": gov.time_cost, "p": gov.parallelism},
        action_label     = gov.preset.value,
        humanity_score   = bio.theta,
        entropy_score    = bio.h_exp,
        biometric        = bio,
        honeypot         = honeypot,
        governor         = gov,
        watchdog         = watchdog,
        pipeline_confidence = overall,
        degraded         = degraded,
    )
