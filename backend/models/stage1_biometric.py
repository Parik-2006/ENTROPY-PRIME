"""
Stage 1 — Biometric Interpreter
Translates raw θ / h_exp / latent_vector into a classified BiometricResult.
No ML model needed here: pure rule-based with confidence bands.
"""
from __future__ import annotations
from .contracts import (
    BiometricInput, BiometricResult,
    Confidence, HoneypotVerdict,
    BOT_THETA_HARD, BOT_THETA_SOFT,
)


def run(inp: BiometricInput) -> BiometricResult:
    """
    Input:  BiometricInput
    Output: BiometricResult

    Confidence rules:
      HIGH   — θ far from boundaries (< 0.05 or > 0.60)
      MEDIUM — θ in [0.05, 0.15) or [0.50, 0.60)
      LOW    — θ in the contested band [0.15, 0.50)

    Latent vector missing → confidence capped at MEDIUM.
    """
    theta = float(inp.theta)
    h_exp = float(inp.h_exp)

    # ── Verdict ───────────────────────────────────────────────────────────────
    if theta < BOT_THETA_HARD:
        verdict    = HoneypotVerdict.BOT
        is_bot     = True
        is_suspect = False
    elif theta < BOT_THETA_SOFT:
        verdict    = HoneypotVerdict.SUSPECT
        is_bot     = False
        is_suspect = True
    else:
        verdict    = HoneypotVerdict.HUMAN
        is_bot     = False
        is_suspect = False

    # ── Confidence ────────────────────────────────────────────────────────────
    has_latent = bool(inp.latent_vector) and len(inp.latent_vector) == 32

    if theta < 0.05 or theta > 0.60:
        conf = Confidence.HIGH
    elif (0.05 <= theta < 0.15) or (0.50 <= theta < 0.60):
        conf = Confidence.MEDIUM
    else:
        conf = Confidence.LOW

    # Missing latent vector degrades confidence one step
    if not has_latent and conf == Confidence.HIGH:
        conf = Confidence.MEDIUM

    note_parts = []
    if not has_latent:
        note_parts.append("no latent vector")
    if inp.server_load > 0.85:
        note_parts.append(f"server_load={inp.server_load:.2f}")
    note = "; ".join(note_parts)

    return BiometricResult(
        theta       = theta,
        h_exp       = h_exp,
        server_load = float(inp.server_load),
        verdict     = verdict,
        confidence  = conf,
        is_bot      = is_bot,
        is_suspect  = is_suspect,
        note        = note,
    )
