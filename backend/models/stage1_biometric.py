"""
pipeline/stage1_biometric.py  —  Stage 1: Biometric Interpretation

Translates raw θ (humanity score) and h_exp (entropy) into a classified
BiometricResult with an explicit confidence band.

Decision logic
──────────────
  θ < BOT_THETA_HARD  → BOT  / HIGH confidence
  θ < BOT_THETA_SOFT  → SUSPECT
    │ θ < midpoint    → MEDIUM confidence
    └ else             → LOW confidence (borderline)
  θ ≥ BOT_THETA_SOFT  → HUMAN
    │ θ > 0.85        → HIGH confidence
    └ else             → MEDIUM confidence

Server load is passed through unchanged for downstream stages.
"""
from __future__ import annotations

import logging

from .contracts import (
    BiometricInput,
    BiometricResult,
    BOT_THETA_HARD,
    BOT_THETA_SOFT,
    Confidence,
    HoneypotVerdict,
)

logger = logging.getLogger("entropy_prime.stage1")

_SUSPECT_MID = (BOT_THETA_HARD + BOT_THETA_SOFT) / 2  # 0.20


def run(raw: BiometricInput) -> BiometricResult:
    """
    Classify the incoming signal and return a BiometricResult.
    Never raises — any unexpected value produces a LOW-confidence HUMAN result
    so real users are never locked out by instrumentation noise.
    """
    theta = float(raw.theta)
    h_exp = float(raw.h_exp)

    try:
        if theta < BOT_THETA_HARD:
            return BiometricResult(
                theta       = theta,
                h_exp       = h_exp,
                server_load = raw.server_load,
                verdict     = HoneypotVerdict.BOT,
                confidence  = Confidence.HIGH,
                is_bot      = True,
                is_suspect  = False,
                note        = f"θ={theta:.3f} < BOT_THETA_HARD={BOT_THETA_HARD}",
            )

        if theta < BOT_THETA_SOFT:
            conf = (
                Confidence.MEDIUM if theta < _SUSPECT_MID
                else Confidence.LOW   # borderline — less certain
            )
            return BiometricResult(
                theta       = theta,
                h_exp       = h_exp,
                server_load = raw.server_load,
                verdict     = HoneypotVerdict.SUSPECT,
                confidence  = conf,
                is_bot      = False,
                is_suspect  = True,
                note        = f"θ={theta:.3f} in suspect band",
            )

        # Confirmed human
        conf = Confidence.HIGH if theta > 0.85 else Confidence.MEDIUM
        return BiometricResult(
            theta       = theta,
            h_exp       = h_exp,
            server_load = raw.server_load,
            verdict     = HoneypotVerdict.HUMAN,
            confidence  = conf,
            is_bot      = False,
            is_suspect  = False,
            note        = "",
        )

    except Exception as exc:
        logger.error("[S1] Unexpected error: %s — returning safe HUMAN/LOW", exc)
        return BiometricResult(
            theta       = 0.5,
            h_exp       = h_exp,
            server_load = raw.server_load,
            verdict     = HoneypotVerdict.HUMAN,
            confidence  = Confidence.LOW,
            note        = f"error_fallback: {exc}",
        )
