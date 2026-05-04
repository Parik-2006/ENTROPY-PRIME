"""
pipeline/stage4_watchdog.py  —  Stage 4: Session Watchdog (PPO)

Continuous identity-drift detection.  Called:
  (a) Inline during /score when a 32-dim latent vector is present.
  (b) Standalone for every /session/verify heartbeat.

PPO input vector (10-dim):
  [lv_mean, lv_std, lv_max, lv_min,    — latent-vector statistics (4)
   lv_l2_norm,                           — L2 norm of the latent vector (1)
   e_rec,                                — autoencoder reconstruction error (1)
   trust_score,                          — running trust score (1)
   e_rec_warn, e_rec_crit, trust_crit]  — threshold indicator bits (3)

Action → WatchdogAction mapping:
  0 → OK
  1 → PASSIVE_REAUTH
  2 → DISABLE_SENSITIVE_API
  (3 → FORCE_LOGOUT via fallback rules only)

Fallback rules (when PPO is unavailable or confidence is LOW):
  e_rec > EREC_CRITICAL   OR  trust < TRUST_CRITICAL → FORCE_LOGOUT
  e_rec > EREC_WARN       OR  trust < TRUST_WARN     → PASSIVE_REAUTH
  otherwise                                           → OK
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from .contracts import (
    Confidence,
    EREC_CRITICAL,
    EREC_WARN,
    TRUST_CRITICAL,
    TRUST_WARN,
    WatchdogAction,
    WatchdogResult,
)

logger = logging.getLogger("entropy_prime.stage4")

_ACTION_MAP: dict[int, WatchdogAction] = {
    0: WatchdogAction.OK,
    1: WatchdogAction.PASSIVE_REAUTH,
    2: WatchdogAction.DISABLE_SENSITIVE_API,
}

# PPO confidence threshold: output probability must exceed this to be HIGH
_HIGH_CONF_PROB = 0.75
_MED_CONF_PROB  = 0.55


def run(
    latent_vector: list[float],
    e_rec:         float,
    trust_score:   float,
    ppo_agent,
) -> WatchdogResult:
    """
    Run the PPO watchdog and return a WatchdogResult.
    Falls back to deterministic threshold rules if PPO raises or returns
    low-confidence output.
    """
    # ── Build state ────────────────────────────────────────────────────────────
    try:
        lv    = np.asarray(latent_vector, dtype=np.float32)
        state = _build_state(lv, e_rec, trust_score)
    except Exception as exc:
        logger.warning("[S4] State construction failed: %s — using fallback rules", exc)
        action, conf, reason = _fallback_rules(e_rec, trust_score)
        return WatchdogResult(
            action      = action,
            trust_score = trust_score,
            e_rec       = e_rec,
            confidence  = conf,
            reason      = reason,
        )

    # ── PPO inference ──────────────────────────────────────────────────────────
    try:
        action_idx, prob = _ppo_infer(ppo_agent, state)
        conf             = _prob_to_confidence(prob)

        # Low-confidence PPO → defer to rule-based fallback
        if conf == Confidence.LOW:
            action, conf, reason = _fallback_rules(e_rec, trust_score)
            reason = "low_ppo_confidence: " + reason
        else:
            action = _ACTION_MAP.get(action_idx, WatchdogAction.OK)
            reason = f"ppo:action={action_idx} p={prob:.3f}"

        new_trust = _update_trust(trust_score, action)
        logger.debug("[S4] action=%s trust=%.3f e_rec=%.3f conf=%s", action.value, new_trust, e_rec, conf.value)

        return WatchdogResult(
            action      = action,
            trust_score = new_trust,
            e_rec       = e_rec,
            confidence  = conf,
            reason      = reason,
        )

    except Exception as exc:
        logger.error("[S4] PPO inference failed: %s — fallback rules", exc)
        action, conf, reason = _fallback_rules(e_rec, trust_score)
        return WatchdogResult(
            action      = action,
            trust_score = trust_score,
            e_rec       = e_rec,
            confidence  = conf,
            reason      = f"ppo_error_fallback: {reason}",
        )


# ── Exposed for orchestrator standalone call ───────────────────────────────────

def _fallback_rules(
    e_rec: float, trust_score: float
) -> tuple[WatchdogAction, Confidence, str]:
    """
    Pure threshold logic.  Returns (action, confidence, human-readable reason).
    Exposed at module level so the orchestrator's except block can reuse it.
    """
    if e_rec > EREC_CRITICAL or trust_score < TRUST_CRITICAL:
        return (
            WatchdogAction.FORCE_LOGOUT,
            Confidence.HIGH,
            f"e_rec={e_rec:.3f}>{EREC_CRITICAL} or trust={trust_score:.3f}<{TRUST_CRITICAL}",
        )
    if e_rec > EREC_WARN or trust_score < TRUST_WARN:
        return (
            WatchdogAction.PASSIVE_REAUTH,
            Confidence.MEDIUM,
            f"e_rec={e_rec:.3f}>{EREC_WARN} or trust={trust_score:.3f}<{TRUST_WARN}",
        )
    return (WatchdogAction.OK, Confidence.HIGH, "within_thresholds")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_state(lv: np.ndarray, e_rec: float, trust_score: float) -> np.ndarray:
    """Construct the 10-dim PPO state vector."""
    lv_mean  = float(np.mean(lv))
    lv_std   = float(np.std(lv))
    lv_max   = float(np.max(lv))
    lv_min   = float(np.min(lv))
    lv_norm  = float(np.linalg.norm(lv))
    return np.array(
        [
            lv_mean, lv_std, lv_max, lv_min, lv_norm,
            e_rec, trust_score,
            float(e_rec > EREC_WARN),
            float(e_rec > EREC_CRITICAL),
            float(trust_score < TRUST_CRITICAL),
        ],
        dtype=np.float32,
    )


def _ppo_infer(ppo_agent, state: np.ndarray) -> tuple[int, float]:
    """
    Call the PPO agent. Returns (action_index, max_action_probability).
    Supports agents that return (action, prob), (action,), or just action.
    """
    result = ppo_agent.select_action(state)
    if isinstance(result, (tuple, list)) and len(result) >= 2:
        action_idx, prob = int(result[0]), float(result[1])
    else:
        action_idx = int(result)
        prob       = 0.6   # assume MEDIUM confidence when prob not returned
    return action_idx, prob


def _prob_to_confidence(prob: float) -> Confidence:
    if prob >= _HIGH_CONF_PROB:
        return Confidence.HIGH
    if prob >= _MED_CONF_PROB:
        return Confidence.MEDIUM
    return Confidence.LOW


def _update_trust(current: float, action: WatchdogAction) -> float:
    """Decay trust when action escalates; small recovery on OK."""
    deltas = {
        WatchdogAction.OK:                    -0.02,

        WatchdogAction.PASSIVE_REAUTH:        -0.10,
        WatchdogAction.DISABLE_SENSITIVE_API: -0.25,
        WatchdogAction.FORCE_LOGOUT:          -1.00,
    }
    return max(0.0, min(1.0, current + deltas.get(action, 0.0)))
