"""
Entropy Prime — Pipeline Orchestrator
Sequences stages 1-4 with explicit I/O contracts, confidence propagation,
and degraded-mode tracking. This is the single entry point for /score.

Usage:
    from pipeline.orchestrator import PipelineOrchestrator
    orch = PipelineOrchestrator(dqn, mab, ppo, shadow_secret, session_secret)
    output: PipelineOutput = orch.run(raw_input)
"""
from __future__ import annotations

import hashlib
import hmac as hmac_mod   # aliased to avoid shadowing in _make_session_token
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
    Each call to run() is fully independent (safe for concurrent requests).

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
        Errors within a stage are caught and converted to fallback results,
        and degraded=True is set on the returned output.

        Stage order:
          S1 Biometric → S2 Honeypot → [short-circuit if bot]
          → S3 Governor → S4 Watchdog
        """
        degraded = False

        # ── Stage 1: Biometric Interpretation ────────────────────────────────
        # Translates raw θ / h_exp / latent_vector into a classified result.
        # Failure here is serious — we fall back to a safe HUMAN/LOW guess so
        # the rest of the pipeline still runs (don't lock out real users).
        try:
            bio = s1.run(raw)
            logger.debug(
                "[S1] verdict=%s conf=%s θ=%.3f",
                bio.verdict, bio.confidence, bio.theta,
            )
        except Exception as exc:
            logger.error("[S1] FAILED: %s — using safe defaults", exc)
            bio      = _safe_bio(raw)
            degraded = True

        # ── Stage 2: Honeypot Classification ─────────────────────────────────
        # Routes confirmed bots / high-confidence suspects into shadow mode.
        # MAB picks the deception arm; low MAB counts → degraded flag.
        try:
            honeypot = s2.run(bio, self._mab, self._shadow, raw.ip_address)
            if honeypot.mab_confidence == Confidence.LOW:
                # MAB is still learning — mark as degraded but continue
                degraded = True
            logger.debug(
                "[S2] shadow=%s arm=%d mab_conf=%s",
                honeypot.should_shadow,
                honeypot.mab_arm_selected,
                honeypot.mab_confidence,
            )
        except Exception as exc:
            logger.error("[S2] FAILED: %s — no shadow routing", exc)
            honeypot = _safe_honeypot(bio)
            degraded = True

        # ── Bot short-circuit ─────────────────────────────────────────────────
        # Bots get a synthetic shadow token and an ECONOMY governor preset
        # (cheapest hashing so we don't waste server resources on them).
        # Stages 3 and 4 are intentionally skipped — no point profiling a bot.
        if honeypot.should_shadow:
            gov   = _economy_governor()
            token = honeypot.synthetic_token or _make_session_token(
                # Guard: synthetic_token should always be set when
                # should_shadow=True, but generate a fallback just in case
                # (e.g. if _safe_honeypot accidentally sets should_shadow=True).
                uid    = "bot_" + secrets.token_hex(6),
                lv     = raw.latent_vector,
                secret = self._sess,
            )
            logger.info(
                "[PIPELINE] Bot short-circuit — shadow=True arm=%d",
                honeypot.mab_arm_selected,
            )
            return _assemble(
                raw      = raw,
                bio      = bio,
                honeypot = honeypot,
                gov      = gov,
                watchdog = None,
                token    = token,
                degraded = degraded,
            )

        # ── Stage 3: Resource Governor (DQN) ─────────────────────────────────
        # Selects the Argon2id hardening preset (ECONOMY → PUNISHER).
        # Hard overrides inside s3.run() handle: bot+overload → ECONOMY,
        # confirmed bot+healthy server → HARD.
        try:
            gov = s3.run(bio, self._dqn)
            if gov.fallback:
                degraded = True
            logger.debug(
                "[S3] preset=%s conf=%s fallback=%s",
                gov.preset, gov.confidence, gov.fallback,
            )
        except Exception as exc:
            logger.error("[S3] FAILED: %s — STANDARD preset", exc)
            gov      = _safe_governor()
            degraded = True

        # ── Stage 4: Session Watchdog (PPO) ──────────────────────────────────
        # Optional continuous identity-drift check. Only runs when the caller
        # provides a 32-dim latent vector (first /score call usually won't).
        # Non-fatal: a failure here sets degraded=True but does not abort.
        watchdog: Optional[WatchdogResult] = None
        try:
            if raw.latent_vector and len(raw.latent_vector) == 32:
                watchdog = s4.run(
                    latent_vector = raw.latent_vector,
                    e_rec         = 0.0,   # baseline on first contact
                    trust_score   = 1.0,   # new session starts fully trusted
                    ppo_agent     = self._ppo,
                )
                logger.debug(
                    "[S4] action=%s trust=%.3f e_rec=%.3f conf=%s",
                    watchdog.action, watchdog.trust_score,
                    watchdog.e_rec, watchdog.confidence,
                )
        except Exception as exc:
            logger.warning("[S4] FAILED (non-critical): %s", exc)
            degraded = True

        # ── Token ─────────────────────────────────────────────────────────────
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
        Standalone watchdog call used by the /session/verify heartbeat endpoint.
        Always returns a WatchdogResult (never raises).
        """
        try:
            return s4.run(latent_vector, e_rec, trust_score, self._ppo)
        except Exception as exc:
            logger.error("[S4-standalone] FAILED: %s", exc)
            # Mirror the same fallback path used inside stage4_watchdog itself
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
# Each mirrors the shape that the corresponding stage would have produced,
# but uses conservative safe values so the rest of the pipeline can proceed.

def _safe_bio(raw: BiometricInput) -> BiometricResult:
    """
    Stage-1 fallback. Assumes HUMAN with LOW confidence — never locks a real
    user out due to an instrumentation error. Downstream stages will hedge
    accordingly (LOW confidence propagates through _min_confidence).
    """
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
    """
    Stage-2 fallback. No shadow routing — benefit of doubt to the user.
    mab_arm_selected=-1 signals that no arm was chosen (reward reporting
    skips arm=-1, see update_mab_reward).
    """
    return HoneypotResult(
        should_shadow    = False,
        synthetic_token  = None,
        verdict          = bio.verdict,
        confidence       = Confidence.LOW,
        mab_arm_selected = -1,
        mab_confidence   = Confidence.LOW,
    )


def _safe_governor() -> GovernorResult:
    """
    Stage-3 fallback. STANDARD preset — never too weak, never too punishing.
    fallback=True ensures degraded flag is set by the orchestrator.
    """
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
    """
    Bot short-circuit governor. ECONOMY (cheapest) — bots don't deserve our
    compute. fallback=True because this is always a synthetic/override result.
    """
    return GovernorResult(
        action      = 0,
        preset      = SecurityPreset.ECONOMY,
        memory_kb   = 65_536,
        time_cost   = 2,
        parallelism = 4,
        confidence  = Confidence.HIGH,
        fallback    = True,
    )


# ── Pipeline confidence roll-up ────────────────────────────────────────────────

_CONF_RANK = {Confidence.HIGH: 2, Confidence.MEDIUM: 1, Confidence.LOW: 0}


def _min_confidence(*confs: Confidence) -> Confidence:
    """
    Return the lowest confidence across all active stages.
    A single LOW stage poisons the entire pipeline's confidence rating,
    surfacing to the ops dashboard for review.
    """
    return min(confs, key=lambda c: _CONF_RANK[c])


# ── Token helper ───────────────────────────────────────────────────────────────

def _make_session_token(uid: str, lv: list[float], secret: str) -> str:
    """
    Produces a tamper-evident session token.

    Structure (hex-encoded after the random prefix):
        <8-char random prefix>.<uid>:<unix_ts>:<latent_hash_16>:<hmac_hex>

    - uid            — unique user identifier for this session
    - unix_ts        — integer timestamp (seconds); used for expiry checks
    - latent_hash_16 — first 16 chars of SHA-256 of the latent vector string
                       representation; ties the token to the biometric snapshot
    - hmac_hex       — HMAC-SHA256 of the plain payload with session_secret;
                       server-side verification must recompute and compare
                       before trusting any token field

    Note: hmac_mod alias is used here to prevent the local variable `hmac`
    from shadowing the standard-library import.
    """
    latent_hash = hashlib.sha256(str(lv).encode()).hexdigest()[:16]
    payload     = f"{uid}:{int(time.time())}:{latent_hash}"
    sig         = hmac_mod.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    encoded = (payload + ":" + sig).encode().hex()
    return secrets.token_urlsafe(8) + "." + encoded


# ── Assemble final PipelineOutput ─────────────────────────────────────────────

def _assemble(
    raw:      BiometricInput,
    bio:      BiometricResult,
    honeypot: HoneypotResult,
    gov:      GovernorResult,
    watchdog: Optional[WatchdogResult],
    token:    str,
    degraded: bool,
) -> PipelineOutput:
    """
    Collect per-stage results into the final contract object.

    Confidence roll-up:
      - Gather confidence from every stage that actually ran.
      - Use _min_confidence so a single uncertain stage lowers the whole
        pipeline's rating (conservative: better to over-flag than under-flag).
      - Watchdog is excluded from roll-up when it didn't run (latent missing
        or bot short-circuit) — absence is not uncertainty.
    """
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
