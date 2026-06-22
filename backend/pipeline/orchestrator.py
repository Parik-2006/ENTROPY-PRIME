"""
models/orchestrator.py — PipelineOrchestrator

Runs all 4 stages in sequence and assembles a PipelineOutput.

v3.2 changes
────────────
* gov_ppo_agent and ppo_agent (watchdog) are OPTIONAL — old tests that
  construct PipelineOrchestrator without them continue to work.
* _assemble() wires challenge = honeypot.challenge into PipelineOutput so
  main.py can return it to the client.
* session token generation uses HMAC-SHA256 over (user_id, latent_vector).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from typing import Optional

import numpy as np

try:
    from ..pipeline.contracts import (
        BiometricInput, ChallengePayload, Confidence,
        PipelineOutput, SecurityPreset, WatchdogAction,
    )
    from ..pipeline import stage1_biometric as _s1
    from ..pipeline import stage2_honeypot  as _s2
    from ..pipeline import stage3_governor  as _s3
    from ..pipeline import stage4_watchdog  as _s4
except ImportError:
    from pipeline.contracts import (  # type: ignore
        BiometricInput, ChallengePayload, Confidence,
        PipelineOutput, SecurityPreset, WatchdogAction,
    )
    from pipeline import stage1_biometric as _s1  # type: ignore
    from pipeline import stage2_honeypot  as _s2  # type: ignore
    from pipeline import stage3_governor  as _s3  # type: ignore
    from pipeline import stage4_watchdog  as _s4  # type: ignore

logger = logging.getLogger("entropy_prime.orchestrator")

# Confidence rank for pipeline-level aggregation (higher = more certain)
_CONF_RANK = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}


def _make_session_token(user_id: str, latent_vector: list, secret: str) -> str:
    """HMAC-SHA256 session token tied to user identity and current latent vector."""
    payload = f"{user_id}:{latent_vector[:8]}"
    sig     = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"ep_{sig}_{secrets.token_hex(8)}"


def _economy_governor():
    """Cheapest preset for confirmed bots — no point profiling shadow traffic."""
    try:
        from ..pipeline.contracts import GovernorResult
    except ImportError:
        from pipeline.contracts import GovernorResult  # type: ignore
    return GovernorResult(
        action      = 0,
        preset      = SecurityPreset.ECONOMY,
        memory_kb   = 65_536,
        time_cost   = 2,
        parallelism = 4,
        confidence  = Confidence.HIGH,
        fallback    = True,
    )


class PipelineOrchestrator:
    """
    Four-stage zero-trust pipeline orchestrator.

    Parameters
    ──────────
    dqn_agent      — DQNAgent (Stage 3 preset selection). Required.
    mab_agent      — MABAgent (Stage 2 arm selection). Required.
    gov_ppo_agent  — PPOPolicyAgent for Stage 3 governor action.
                     Optional (defaults to None → no PPO overlay in Stage 3).
    ppo_agent      — PPOAgent for Stage 4 watchdog.
                     Optional (defaults to a fresh cold-start PPOAgent).
    shadow_secret  — HMAC secret for challenge signing.
    session_secret — HMAC secret for session token generation.
    """

    def __init__(
        self,
        dqn_agent,
        mab_agent,
        gov_ppo_agent=None,
        ppo_agent=None,
        shadow_secret: str = "",
        session_secret: str = "",
    ) -> None:
        self._dqn            = dqn_agent
        self._mab            = mab_agent
        self._gov_ppo        = gov_ppo_agent      # may be None
        self._ppo            = ppo_agent          # resolved below
        self._shadow_secret  = shadow_secret
        self._session_secret = session_secret

        # If no watchdog PPO supplied, create a cold-start agent so the
        # stage never crashes — it will use random weights until a checkpoint
        # is loaded.
        if self._ppo is None:
            try:
                from ..models.ppo import PPOAgent
            except ImportError:
                from models.ppo import PPOAgent  # type: ignore
            self._ppo = PPOAgent(state_dim=10, action_dim=3)
            logger.debug("[Orchestrator] No ppo_agent supplied — using cold-start PPOAgent")

    # ── Full pipeline ─────────────────────────────────────────────────────────

    def run(self, raw: BiometricInput) -> PipelineOutput:
        """
        Execute Stages 1–4 and return a fully assembled PipelineOutput.
        Always returns without raising; degraded=True signals partial failure.
        """
        degraded = False

        # Stage 1 — biometric
        try:
            bio = _s1.run(raw)
        except Exception as exc:
            logger.error("[S1] Failed: %s", exc)
            try:
                from ..pipeline.contracts import BiometricResult, HoneypotVerdict
            except ImportError:
                from pipeline.contracts import BiometricResult, HoneypotVerdict  # type: ignore
            bio      = BiometricResult(
                verdict=HoneypotVerdict.SUSPECT, confidence=Confidence.LOW,
                is_bot=False, theta=raw.theta, h_exp=raw.h_exp,
                note="stage1_error",
            )
            degraded = True

        # Stage 2 — honeypot / MAB
        try:
            honeypot = _s2.run(bio, self._mab, self._shadow_secret)
        except Exception as exc:
            logger.error("[S2] Failed: %s", exc)
            try:
                from ..pipeline.contracts import HoneypotResult
            except ImportError:
                from pipeline.contracts import HoneypotResult  # type: ignore
            honeypot = HoneypotResult(should_shadow=False, mab_arm_selected=-1,
                                      mab_confidence=Confidence.LOW, challenge=None)
            degraded = True

        # Bot short-circuit — shadow-routed bots skip Stages 3/4 and use ECONOMY.
        if honeypot.should_shadow:
            return self._assemble(
                raw, bio, honeypot, _economy_governor(), None, degraded,
            )

        # Stage 3 — resource governor
        try:
            governor = _s3.run(bio, self._dqn, ppo_agent=self._gov_ppo)
            degraded = degraded or bool(getattr(governor, "fallback", False))
        except Exception as exc:
            logger.error("[S3] Failed: %s", exc)
            try:
                from ..pipeline.contracts import GovernorResult
            except ImportError:
                from pipeline.contracts import GovernorResult  # type: ignore
            governor = GovernorResult(
                preset=SecurityPreset.STANDARD, memory_kb=128*1024,
                time_cost=2, parallelism=4, confidence=Confidence.LOW, fallback=True,
            )
            degraded = True

        # Stage 4 — session watchdog (only on non-bot traffic)
        watchdog = None
        if not honeypot.should_shadow:
            try:
                watchdog = _s4.run(
                    latent_vector = raw.latent_vector or [0.0] * 32,
                    e_rec         = raw.h_exp,
                    trust_score   = 1.0,
                    ppo_agent     = self._ppo,
                )
            except Exception as exc:
                logger.error("[S4] Failed: %s", exc)
                degraded = True

        return self._assemble(raw, bio, honeypot, governor, watchdog, degraded)

    # ── Watchdog-only path (heartbeat) ────────────────────────────────────────

    def run_watchdog(
        self,
        latent_vector: list[float],
        e_rec:         float,
        trust_score:   float,
    ):
        """
        Run only Stage 4 (watchdog heartbeat).
        Called by /session/verify with the DB-sourced trust score.
        """
        return _s4.run(latent_vector, e_rec, trust_score, self._ppo)

    # ── MAB reward feedback ───────────────────────────────────────────────────

    def report_mab_reward(self, arm: int, reward: float) -> None:
        self._mab.update(arm, reward)

    # ── Assembly ──────────────────────────────────────────────────────────────

    def _assemble(
        self,
        raw,
        bio,
        honeypot,
        governor,
        watchdog,
        degraded: bool,
    ) -> PipelineOutput:
        shadow_mode = honeypot.should_shadow

        # Phase 3 MVP — Synthetic Success Injection (Feature 1):
        # Shadow sessions now receive a token in the SAME format as a genuine
        # session token (ep_<hmac>_<rand>).  No "bot_"/"ep_shadow_" marker is
        # placed on the wire, so an attacker cannot detect shadow mode by
        # inspecting their token.  The "this is shadow" fact is tracked
        # server-side (framework.deception.synthetic_success.ShadowStateStore,
        # registered by main.py) and via PipelineOutput.shadow_mode for the
        # defender dashboard only.
        token = _make_session_token("anon", raw.latent_vector, self._session_secret)

        argon2_params = {
            "time_cost":   governor.time_cost,
            "memory_kb":   governor.memory_kb,
            "parallelism": governor.parallelism,
        }

        # Pipeline-level confidence: minimum across stages
        confs = [bio.confidence, honeypot.mab_confidence, governor.confidence]
        if watchdog:
            confs.append(watchdog.confidence)
        pipeline_conf = min(confs, key=lambda c: _CONF_RANK[c])

        # Human-readable action label
        action_label = governor.preset.value

        # ── Wire challenge from honeypot into output ──────────────────────────
        # This was missing before v3.2: main.py checks result.challenge and
        # includes it in the response — it must come from honeypot.challenge.
        challenge: Optional[ChallengePayload] = honeypot.challenge

        return PipelineOutput(
            session_token       = token,
            shadow_mode         = shadow_mode,
            argon2_params       = argon2_params,
            humanity_score      = bio.theta,
            entropy_score       = bio.h_exp,
            action_label        = action_label,
            pipeline_confidence = pipeline_conf,
            degraded            = degraded,
            biometric           = bio,
            honeypot            = honeypot,
            governor            = governor,
            watchdog            = watchdog,
            challenge           = challenge,    # ← fix: was not included before
            mab_arm             = honeypot.mab_arm_selected,
        )
