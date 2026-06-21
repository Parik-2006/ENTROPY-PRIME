"""
pipeline/stage4_watchdog.py  —  Stage 4: Session Watchdog (PPO)

Continuous identity-drift detection.  Called:
  (a) Inline during /score when a 32-dim latent vector is present.
  (b) Standalone for every /session/verify heartbeat.

Cross-site threat intelligence gate
────────────────────────────────────
`run_with_threat_gate()` is the recommended entry point for all production
callers.  It checks the global threat-intelligence blocklist FIRST (via
WatchdogService) before running the local PPO, and ingests the PPO result
back into the cross-site system afterward.  Per-session PPO is skipped and
FORCE_LOGOUT is returned immediately for any globally flagged identity.

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


# ── Primary entry point (with cross-site threat gate) ─────────────────────────

async def run_with_threat_gate(
    latent_vector:   list[float],
    e_rec:           float,
    trust_score:     float,
    ppo_agent,
    *,
    watchdog_service,           # WatchdogService instance
    tenant_id:       str,
    fingerprint:     str,
    ip_address:      Optional[str] = None,
) -> WatchdogResult:
    """
    Full pipeline entry point combining cross-site threat intelligence with
    the per-session PPO watchdog.

    Flow
    ────
    1. Query the global blocklist.  If the fingerprint or IP is already
       globally flagged, short-circuit to FORCE_LOGOUT without running PPO.
    2. Run the per-session PPO watchdog (same logic as `run()`).
    3. Ingest the result into the threat-intelligence layer so it can
       contribute to cross-site threat scoring.
    4. Return the WatchdogResult to the caller.

    Args:
        latent_vector:    32-dim identity embedding from the upstream encoder.
        e_rec:            Autoencoder reconstruction error for this session.
        trust_score:      Running trust score (0.0–1.0).
        ppo_agent:        PPO agent instance; must expose `select_action(state)`.
        watchdog_service: Injected WatchdogService (FastAPI dependency).
        tenant_id:        Identifier of the SaaS tenant making the request.
        fingerprint:      Raw device/browser fingerprint string.
        ip_address:       Client IP address (optional but recommended).
    """
    # ── Step 1: Global threat gate ────────────────────────────────────────────
    gate_result = await watchdog_service.is_globally_flagged(fingerprint, ip_address)
    if gate_result.globally_flagged:
        logger.warning(
            "[S4] GLOBAL THREAT GATE triggered tenant=%s fp=%.8s reason=%s",
            tenant_id,
            gate_result.fingerprint_hash,
            gate_result.reason,
        )
        result = WatchdogResult(
            action      = WatchdogAction.FORCE_LOGOUT,
            trust_score = 0.0,
            e_rec       = e_rec,
            confidence  = Confidence.HIGH,
            reason      = f"global_threat_gate: {gate_result.reason}",
        )
        # Still ingest so the cross-site score keeps accumulating
        await watchdog_service.ingest(tenant_id, fingerprint, ip_address, result)
        return result

    # ── Step 2: Per-session PPO watchdog ──────────────────────────────────────
    result = run(latent_vector, e_rec, trust_score, ppo_agent)

    # ── Step 3: Ingest into cross-site threat intelligence ────────────────────
    await watchdog_service.ingest(tenant_id, fingerprint, ip_address, result)

    return result


# ── Standalone entry point (no threat gate, backwards-compatible) ─────────────

def run(
    latent_vector: list[float],
    e_rec:         float,
    trust_score:   float,
    ppo_agent,
) -> WatchdogResult:
    """
    Run the PPO watchdog and return a WatchdogResult.

    This synchronous function is intentionally kept free of cross-site
    concerns so it can be unit-tested and called from contexts that don't
    have a WatchdogService available (e.g. offline batch re-scoring).

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
        logger.debug(
            "[S4] action=%s trust=%.3f e_rec=%.3f conf=%s",
            action.value, new_trust, e_rec, conf.value,
        )

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
        WatchdogAction.OK:                     0.02,
        WatchdogAction.PASSIVE_REAUTH:        -0.10,
        WatchdogAction.DISABLE_SENSITIVE_API: -0.25,
        WatchdogAction.FORCE_LOGOUT:          -1.00,
    }
    return max(0.0, min(1.0, current + deltas.get(action, 0.0)))