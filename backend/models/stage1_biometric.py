"""
models/stage1_biometric.py  —  Stage 1: Biometric Interpretation (SaaS Edition)

Translates a ContextualBiometricInput into a BiometricResult that is aware of:

  • which tenant site the signal comes from  (context.site_id)
  • which end-user produced it              (context.user_id)
  • whether that user is still in the       (learning_phase flag)
    learning phase on this site
  • how close the current embedding is to   (centroid_dist)
    the user's stored human centroid

Decision logic
──────────────

  [Learning phase]
    → LEARNING / LOW — we observe but never block; the centroid is still
      being built.  centroid_dist may be None (no centroid yet).

  [Graduated user — normal classification]

    θ < BOT_THETA_HARD
      → BOT / HIGH

    θ < BOT_THETA_SOFT
      → SUSPECT
        · θ < midpoint    → MEDIUM confidence
        · else            → LOW  (borderline)

    θ ≥ BOT_THETA_SOFT
      → HUMAN
        · centroid_dist available and low (< CENTROID_CLOSE_THRESHOLD)
            + θ > 0.85 + latent vector present → HIGH
            + otherwise                        → MEDIUM
        · centroid_dist high or unavailable
            + θ > 0.85 + latent vector present → MEDIUM  (centroid mismatch
              reduces confidence one level)           or profile drift warning
            + else                             → LOW
        · [BOT_THETA_SOFT, 0.50) is always LOW regardless of centroid

Backward compatibility
──────────────────────
The original `run(raw: BiometricInput)` signature still works via the thin
`run_legacy()` shim at the bottom of this file.  All new call-sites should
use `run(inp: ContextualBiometricInput)`.
"""
from __future__ import annotations

import logging
from typing import Optional

from .contracts import (
    BiometricContext,
    BiometricResult,
    BOT_THETA_HARD,
    BOT_THETA_SOFT,
    Confidence,
    ContextualBiometricInput,
    HoneypotVerdict,
)

logger = logging.getLogger("entropy_prime.stage1")

# ── Tuning constants ──────────────────────────────────────────────────────────

_SUSPECT_MID = (BOT_THETA_HARD + BOT_THETA_SOFT) / 2   # 0.20

# Cosine distance below which we consider the embedding "close" to the stored
# human centroid, adding a confidence boost.
CENTROID_CLOSE_THRESHOLD: float = 0.25

# When centroid distance exceeds this, log a profile-drift warning.
CENTROID_DRIFT_THRESHOLD: float = 0.65


# ── Main entry point ──────────────────────────────────────────────────────────

def run(inp: ContextualBiometricInput) -> BiometricResult:
    """
    Classify the incoming contextual signal.

    Never raises — unexpected values fall back to a LOW-confidence HUMAN so
    real users are never locked out by instrumentation noise.
    """
    theta    = float(inp.theta)
    h_exp    = float(inp.h_exp)
    has_latent  = bool(inp.latent_vector)
    ctx      = inp.context
    cdist: Optional[float] = inp.centroid_dist

    try:
        # ── Learning phase: observe only, never block ─────────────────────
        if inp.learning_phase:
            note = (
                f"learning_phase: user={ctx.user_id!r} site={ctx.site_id!r} "
                f"θ={theta:.3f} cdist={'n/a' if cdist is None else f'{cdist:.3f}'}"
            )
            logger.debug("[S1] %s", note)
            return BiometricResult(
                theta        = theta,
                h_exp        = h_exp,
                server_load  = inp.server_load,
                verdict      = HoneypotVerdict.LEARNING,
                confidence   = Confidence.LOW,
                is_bot       = False,
                is_suspect   = False,
                note         = note,
                context      = ctx,
                centroid_dist= cdist,
            )

        # ── Hard bot ──────────────────────────────────────────────────────
        if theta < BOT_THETA_HARD:
            return BiometricResult(
                theta        = theta,
                h_exp        = h_exp,
                server_load  = inp.server_load,
                verdict      = HoneypotVerdict.BOT,
                confidence   = Confidence.HIGH,
                is_bot       = True,
                is_suspect   = False,
                note         = (
                    f"θ={theta:.3f} < BOT_THETA_HARD={BOT_THETA_HARD} "
                    f"site={ctx.site_id!r}"
                ),
                context      = ctx,
                centroid_dist= cdist,
            )

        # ── Suspect band ──────────────────────────────────────────────────
        if theta < BOT_THETA_SOFT:
            conf = (
                Confidence.MEDIUM if theta < _SUSPECT_MID
                else Confidence.LOW
            )
            return BiometricResult(
                theta        = theta,
                h_exp        = h_exp,
                server_load  = inp.server_load,
                verdict      = HoneypotVerdict.SUSPECT,
                confidence   = conf,
                is_bot       = False,
                is_suspect   = True,
                note         = (
                    f"θ={theta:.3f} in suspect band "
                    f"site={ctx.site_id!r} user={ctx.user_id!r}"
                ),
                context      = ctx,
                centroid_dist= cdist,
            )

        # ── Confirmed human — determine confidence ────────────────────────
        # Sub-band [BOT_THETA_SOFT, 0.50): barely past the threshold → always LOW
        if theta < 0.50:
            conf = Confidence.LOW
            _maybe_warn_drift(cdist, ctx)
            return BiometricResult(
                theta        = theta,
                h_exp        = h_exp,
                server_load  = inp.server_load,
                verdict      = HoneypotVerdict.HUMAN,
                confidence   = Confidence.LOW,
                is_bot       = False,
                is_suspect   = False,
                note         = f"borderline_human θ={theta:.3f} site={ctx.site_id!r}",
                context      = ctx,
                centroid_dist= cdist,
            )

        # θ ∈ [0.50, 0.85] or θ > 0.85 — centroid distance modulates confidence
        conf = _human_confidence(theta, has_latent, cdist, ctx)

        return BiometricResult(
            theta        = theta,
            h_exp        = h_exp,
            server_load  = inp.server_load,
            verdict      = HoneypotVerdict.HUMAN,
            confidence   = conf,
            is_bot       = False,
            is_suspect   = False,
            note         = "" if has_latent else "no_latent_vector",
            context      = ctx,
            centroid_dist= cdist,
        )

    except Exception as exc:
        logger.error(
            "[S1] Unexpected error for site=%r user=%r: %s — returning safe HUMAN/LOW",
            ctx.site_id, ctx.user_id, exc,
        )
        return BiometricResult(
            theta        = 0.5,
            h_exp        = h_exp,
            server_load  = inp.server_load,
            verdict      = HoneypotVerdict.HUMAN,
            confidence   = Confidence.LOW,
            note         = f"error_fallback: {exc}",
            context      = ctx,
            centroid_dist= cdist,
        )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _human_confidence(
    theta: float,
    has_latent: bool,
    cdist: Optional[float],
    ctx,
) -> Confidence:
    """
    Map (θ, latent_present, centroid_distance) → Confidence for the HUMAN path.

    Centroid distance acts as a second signal:
      • close (< CENTROID_CLOSE_THRESHOLD) → trust boost
      • far   (> CENTROID_DRIFT_THRESHOLD) → trust penalty + warning
      • None (no centroid stored yet)       → neutral (treat as medium distance)
    """
    centroid_close = (cdist is not None) and (cdist < CENTROID_CLOSE_THRESHOLD)
    centroid_far   = (cdist is None) or (cdist > CENTROID_DRIFT_THRESHOLD)

    if centroid_far:
        _maybe_warn_drift(cdist, ctx)

    if theta > 0.85 and has_latent:
        # Strong θ + latent vector
        if centroid_close:
            return Confidence.HIGH
        if centroid_far:
            # Centroid mismatch tempers confidence — could be profile drift
            # or a shared device; bump down one level
            return Confidence.MEDIUM
        return Confidence.MEDIUM   # centroid in the middle zone

    # θ ∈ [0.50, 0.85] or missing latent
    if centroid_close:
        return Confidence.MEDIUM   # centroid boost brings borderline up
    return Confidence.LOW


def _maybe_warn_drift(cdist: Optional[float], ctx) -> None:
    """Emit a warning when centroid distance suggests possible profile drift."""
    if cdist is not None and cdist > CENTROID_DRIFT_THRESHOLD:
        logger.warning(
            "[S1] Profile drift detected: site=%r user=%r cdist=%.3f > %.3f",
            ctx.site_id, ctx.user_id, cdist, CENTROID_DRIFT_THRESHOLD,
        )


# ── Legacy shim ───────────────────────────────────────────────────────────────

def run_legacy(raw) -> BiometricResult:  # raw: BiometricInput
    """
    Backward-compatible wrapper so existing call-sites keep working unchanged.

    Wraps the old BiometricInput in a ContextualBiometricInput with an empty
    context and learning_phase=False, then delegates to run().
    """
    inp = ContextualBiometricInput(
        theta          = raw.theta,
        h_exp          = raw.h_exp,
        server_load    = raw.server_load,
        latent_vector  = raw.latent_vector or [],
        context        = BiometricContext(site_id="", user_id=""),
        learning_phase = False,
        centroid_dist  = None,
    )
    return run(inp)