"""
pipeline/stage3_governor.py  —  Stage 3: Resource Governor (DQN)

Selects the Argon2id hardening preset (ECONOMY → PUNISHER) based on the
biometric classification and current server load.

DQN action → preset mapping
──────────────────────────
  0  ECONOMY   64 MB / t=2 / p=4    — bots, high-load fallback
  1  STANDARD 128 MB / t=3 / p=4    — default for legitimate users
  2  HARD     256 MB / t=4 / p=8    — elevated-risk sessions
  3  PUNISHER 512 MB / t=5 / p=8    — maximum hardening (suspicious human)

Hard overrides (bypass DQN entirely):
  • Bot + server_load > SERVER_LOAD_HIGH → ECONOMY (save resources)
  • Bot + healthy server                 → HARD    (punish scrapers)
  • MEDIUM/LOW confidence from S1        → STANDARD (conservative)
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from .contracts import (
    BiometricResult,
    Confidence,
    GovernorResult,
    HoneypotVerdict,
    SecurityPreset,
    SERVER_LOAD_HIGH,
)

logger = logging.getLogger("entropy_prime.stage3")

# ── Argon2id preset table ──────────────────────────────────────────────────────
_PRESETS: dict[int, tuple[SecurityPreset, int, int, int]] = {
    #           preset           memory_kb   time_cost  parallelism
    0: (SecurityPreset.ECONOMY,   65_536,     2,         4),
    1: (SecurityPreset.STANDARD, 131_072,     3,         4),
    2: (SecurityPreset.HARD,     262_144,     4,         8),
    3: (SecurityPreset.PUNISHER, 524_288,     5,         8),
}

_DEFAULT_ACTION = 1   # STANDARD


def run(bio: BiometricResult, dqn_agent) -> GovernorResult:
    """
    Determine the Argon2id preset for this request.

    Returns a GovernorResult; never raises.  A fallback result is returned
    with fallback=True if the DQN errors so the orchestrator can set degraded=True.
    """
    # ── Hard overrides ─────────────────────────────────────────────────────────
    override = _hard_override(bio)
    if override is not None:
        preset, mem, tc, par = _PRESETS[override]
        logger.debug("[S3] Hard override → action=%d (%s)", override, preset.value)
        return GovernorResult(
            action      = override,
            preset      = preset,
            memory_kb   = mem,
            time_cost   = tc,
            parallelism = par,
            confidence  = Confidence.HIGH,
            fallback    = True,   # override is still a "fallback" from DQN's perspective
        )

    # ── DQN inference ─────────────────────────────────────────────────────────
    try:
        state  = _build_state(bio)
        action = int(dqn_agent.select_action(state))
        action = max(0, min(3, action))          # clamp to valid range
        conf   = _action_confidence(bio, action)
        preset, mem, tc, par = _PRESETS[action]
        logger.debug("[S3] DQN → action=%d (%s) conf=%s", action, preset.value, conf.value)
        return GovernorResult(
            action      = action,
            preset      = preset,
            memory_kb   = mem,
            time_cost   = tc,
            parallelism = par,
            confidence  = conf,
            fallback    = False,
        )
    except Exception as exc:
        logger.error("[S3] DQN inference failed: %s — STANDARD fallback", exc)
        preset, mem, tc, par = _PRESETS[_DEFAULT_ACTION]
        return GovernorResult(
            action      = _DEFAULT_ACTION,
            preset      = preset,
            memory_kb   = mem,
            time_cost   = tc,
            parallelism = par,
            confidence  = Confidence.LOW,
            fallback    = True,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hard_override(bio: BiometricResult) -> Optional[int]:
    """Return a fixed action index when business rules supersede the DQN."""
    if bio.is_bot:
        # Bots on an overloaded server → ECONOMY (don't waste compute)
        if bio.server_load > SERVER_LOAD_HIGH:
            return 0
        # Bots on a healthy server → HARD (punish scraping attempts)
        return 2

    # Low-confidence classification → conservative STANDARD
    if bio.confidence == Confidence.LOW:
        return 1

    return None  # no override — let the DQN decide


def _build_state(bio: BiometricResult) -> np.ndarray:
    """
    3-element state vector for the DQN:
      [theta, server_load, is_suspect_float]
    """
    return np.array(
        [bio.theta, bio.server_load, float(bio.is_suspect)],
        dtype=np.float32,
    )


def _action_confidence(bio: BiometricResult, action: int) -> Confidence:
    """
    Map biometric confidence + action to an overall confidence band.
    We trust the DQN more when the biometric signal is strong.
    """
    if bio.confidence == Confidence.HIGH:
        return Confidence.HIGH
    if bio.confidence == Confidence.MEDIUM:
        return Confidence.MEDIUM
    return Confidence.LOW
