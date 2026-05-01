"""
Stage 3 — Resource Governor (DQN)
Selects the Argon2id hardening preset based on the biometric signal and
server load. Falls back to STANDARD when DQN is unavailable or uncertain.

Input contract:  BiometricResult
Output contract: GovernorResult
"""
from __future__ import annotations
import numpy as np
from .contracts import (
    BiometricResult, GovernorResult,
    Confidence, SecurityPreset,
    SERVER_LOAD_HIGH,
)


# ── Argon2id param table ──────────────────────────────────────────────────────
PRESETS: dict[int, tuple[SecurityPreset, int, int, int]] = {
    # action → (preset, memory_kb, time_cost, parallelism)
    0: (SecurityPreset.ECONOMY,  65_536,    2,  4),
    1: (SecurityPreset.STANDARD, 131_072,   3,  4),
    2: (SecurityPreset.HARD,     524_288,   4,  8),
    3: (SecurityPreset.PUNISHER, 1_048_576, 8, 16),
}

# Safe default when model is missing/uncertain
FALLBACK_ACTION = 1  # STANDARD


def run(bio: BiometricResult, dqn_agent) -> GovernorResult:
    """
    Fallback rules (applied before DQN):
      - is_bot and server overloaded → ECONOMY (don't waste resources)
      - is_bot and server fine       → HARD (burn attacker resources)
      - server_load > HIGH           → cap at STANDARD regardless of DQN

    DQN override: if bio.confidence is LOW, DQN output is accepted but
    GovernorResult.confidence is set to MEDIUM (hedged).

    If DQN is None or raises, FALLBACK_ACTION is used and fallback=True.
    """
    # ── Hard override: bot + overloaded server ────────────────────────────────
    if bio.is_bot and bio.server_load > SERVER_LOAD_HIGH:
        return _make_result(0, fallback=True, conf=Confidence.HIGH,
                            reason="bot+overload → economy")

    # ── Hard override: definite bot, server healthy → burn resources ──────────
    if bio.is_bot and bio.confidence == Confidence.HIGH:
        return _make_result(2, fallback=True, conf=Confidence.HIGH,
                            reason="confirmed bot → hard")

    # ── DQN ───────────────────────────────────────────────────────────────────
    action, dqn_conf, used_fallback = _dqn_select(dqn_agent, bio)

    # ── Server load cap ───────────────────────────────────────────────────────
    if bio.server_load > SERVER_LOAD_HIGH and action > 1:
        action        = 1           # clamp to STANDARD
        dqn_conf      = Confidence.MEDIUM
        used_fallback = True

    # ── Propagate bio confidence through ─────────────────────────────────────
    if bio.confidence == Confidence.LOW and dqn_conf == Confidence.HIGH:
        dqn_conf = Confidence.MEDIUM   # input was noisy; hedge output

    return _make_result(action, fallback=used_fallback, conf=dqn_conf)


# ── Internals ─────────────────────────────────────────────────────────────────

def _dqn_select(dqn_agent, bio: BiometricResult) -> tuple[int, Confidence, bool]:
    if dqn_agent is None:
        return FALLBACK_ACTION, Confidence.LOW, True
    try:
        state  = np.array([bio.theta, bio.h_exp, bio.server_load], dtype=np.float32)
        action = int(dqn_agent.select_action(state))
        # Measure Q-value spread as a proxy for confidence
        q_vals = dqn_agent.q_values(state)          # returns np.ndarray [4]
        spread = float(np.max(q_vals) - np.min(q_vals))
        if spread > 1.5:
            conf = Confidence.HIGH
        elif spread > 0.5:
            conf = Confidence.MEDIUM
        else:
            conf = Confidence.LOW
        return action, conf, False
    except Exception:
        return FALLBACK_ACTION, Confidence.LOW, True


def _make_result(action: int, *, fallback: bool, conf: Confidence,
                 reason: str = "") -> GovernorResult:
    preset, mem, t, p = PRESETS[action]
    return GovernorResult(
        action      = action,
        preset      = preset,
        memory_kb   = mem,
        time_cost   = t,
        parallelism = p,
        confidence  = conf,
        fallback    = fallback,
    )
