"""
Stage 4 — Session Watchdog (PPO)
Continuous identity-drift detector. Runs on every heartbeat (not every /score).
Uses PPO policy to recommend an action from {ok, passive_reauth,
disable_sensitive_apis, force_logout}.

Input contract:  latent_vector (32-dim), e_rec (float), trust_score (float)
Output contract: WatchdogResult
"""
from __future__ import annotations
import numpy as np
import torch
from .contracts import (
    WatchdogResult, WatchdogAction, Confidence,
    EREC_WARN, EREC_CRITICAL, TRUST_WARN, TRUST_CRITICAL,
)

# PPO action index → WatchdogAction
PPO_ACTION_MAP: dict[int, WatchdogAction] = {
    0: WatchdogAction.OK,
    1: WatchdogAction.PASSIVE_REAUTH,
    2: WatchdogAction.DISABLE_SENSITIVE_API,
}

# Hard overrides that bypass PPO entirely
def _hard_override(e_rec: float, trust: float) -> WatchdogAction | None:
    if trust < TRUST_CRITICAL and e_rec > EREC_CRITICAL:
        return WatchdogAction.FORCE_LOGOUT
    return None


def run(
    latent_vector: list[float],
    e_rec:         float,
    trust_score:   float,
    ppo_agent,                # PPOAgent or None
) -> WatchdogResult:
    """
    Decision ladder:
      1. Hard override (trust critical + e_rec critical) → FORCE_LOGOUT
      2. PPO policy on 10-dim state vector
      3. Fallback rules when PPO is unavailable or low-confidence

    State vector fed to PPO (10-dim):
      [e_rec, trust_score, trust_delta_proxy,
       latent_norm, latent_mean, latent_std,
       e_rec_gt_warn, e_rec_gt_critical, trust_gt_warn, trust_gt_critical]
    """
    # ── Hard override ─────────────────────────────────────────────────────────
    override = _hard_override(e_rec, trust_score)
    if override is not None:
        return WatchdogResult(
            action      = override,
            trust_score = trust_score,
            e_rec       = e_rec,
            confidence  = Confidence.HIGH,
            reason      = "hard_override: critical drift+trust",
        )

    # ── PPO ───────────────────────────────────────────────────────────────────
    action, conf, reason = _ppo_decision(latent_vector, e_rec, trust_score, ppo_agent)

    return WatchdogResult(
        action      = action,
        trust_score = trust_score,
        e_rec       = e_rec,
        confidence  = conf,
        reason      = reason,
    )


# ── Internals ─────────────────────────────────────────────────────────────────

def _build_state(latent_vector: list[float], e_rec: float, trust: float) -> np.ndarray:
    lv   = np.array(latent_vector, dtype=np.float32) if latent_vector else np.zeros(32)
    norm = float(np.linalg.norm(lv))
    mean = float(np.mean(lv))
    std  = float(np.std(lv))
    return np.array([
        e_rec,
        trust,
        1.0 - trust,                         # delta proxy (simplified)
        min(norm / 10.0, 1.0),
        mean,
        std,
        float(e_rec > EREC_WARN),
        float(e_rec > EREC_CRITICAL),
        float(trust < TRUST_WARN),
        float(trust < TRUST_CRITICAL),
    ], dtype=np.float32)


def _ppo_decision(
    latent_vector: list[float],
    e_rec: float,
    trust: float,
    ppo_agent,
) -> tuple[WatchdogAction, Confidence, str]:
    """Returns (action, confidence, reason)."""
    if ppo_agent is None:
        return _fallback_rules(e_rec, trust)

    try:
        state        = _build_state(latent_vector, e_rec, trust)
        state_tensor = torch.FloatTensor(state).unsqueeze(0)
        with torch.no_grad():
            probs = ppo_agent.policy(state_tensor).squeeze()
        probs_np   = probs.numpy()
        best_idx   = int(np.argmax(probs_np))
        best_prob  = float(probs_np[best_idx])

        # Confidence from probability mass on top action
        if best_prob >= 0.70:
            conf = Confidence.HIGH
        elif best_prob >= 0.45:
            conf = Confidence.MEDIUM
        else:
            conf = Confidence.LOW

        # Low-confidence PPO → fall back to rules
        if conf == Confidence.LOW:
            fb_action, fb_conf, fb_reason = _fallback_rules(e_rec, trust)
            return fb_action, fb_conf, f"ppo_low_conf→{fb_reason}"

        action = PPO_ACTION_MAP.get(best_idx, WatchdogAction.PASSIVE_REAUTH)
        return action, conf, f"ppo p={best_prob:.3f}"

    except Exception as exc:
        return _fallback_rules(e_rec, trust)


def _fallback_rules(e_rec: float, trust: float) -> tuple[WatchdogAction, Confidence, str]:
    """
    Deterministic rule ladder used when PPO is missing or uncertain.
    Always returns HIGH confidence (rules are unambiguous).
    """
    if trust < TRUST_CRITICAL or e_rec > EREC_CRITICAL:
        return WatchdogAction.DISABLE_SENSITIVE_API, Confidence.HIGH, "fallback:critical"
    if trust < TRUST_WARN or e_rec > EREC_WARN:
        return WatchdogAction.PASSIVE_REAUTH, Confidence.HIGH, "fallback:warn"
    return WatchdogAction.OK, Confidence.HIGH, "fallback:ok"
