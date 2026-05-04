"""
pipeline/stage2_honeypot.py  —  Stage 2: Honeypot Classification

Routes confirmed bots and high-confidence suspects into shadow mode.
A Multi-Armed Bandit (MAB) selects the deception strategy (arm) each time.

Arms:
  0 — slow honeypot  (Tarpit: delayed responses, fake captchas)
  1 — mirror honeypot (Echo: reflects plausible-looking data)
  2 — canary honeypot (Audit: logs everything silently, fast responses)

Shadow tokens are HMAC-signed synthetic session tokens that look identical
to real ones — bots cannot distinguish themselves via the HTTP response.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from typing import Optional

from .contracts import (
    BiometricResult,
    BOT_THETA_HARD,
    BOT_THETA_SOFT,
    Confidence,
    HoneypotResult,
    HoneypotVerdict,
)

logger = logging.getLogger("entropy_prime.stage2")

# MAB arm confidence threshold: if the winning arm has been selected fewer
# than MIN_ARM_PULLS times the result is LOW confidence (still learning).
_MIN_ARM_PULLS = 10


def run(
    bio:        BiometricResult,
    mab_agent,          # MABAgent instance
    shadow_secret: str,
    ip_address:    str = "?",
) -> HoneypotResult:
    """
    Decide whether to shadow-route the request and, if so, which MAB arm to use.

    Shadow routing is triggered when:
      • verdict == BOT   (always)
      • verdict == SUSPECT  AND  confidence == HIGH or MEDIUM

    A SUSPECT with LOW confidence gets the benefit of the doubt — no shadow.
    """
    should_shadow = _should_shadow(bio)

    if not should_shadow:
        return HoneypotResult(
            should_shadow    = False,
            synthetic_token  = None,
            verdict          = bio.verdict,
            confidence       = bio.confidence,
            mab_arm_selected = -1,
            mab_confidence   = Confidence.HIGH,  # no MAB needed → deterministically not shadowed
        )

    # ── Select MAB arm ────────────────────────────────────────────────────────
    arm, mab_conf = _select_arm(mab_agent)

    # ── Generate synthetic shadow token ───────────────────────────────────────
    token = _make_shadow_token(ip_address, arm, shadow_secret)

    logger.info(
        "[S2] Shadow routing: verdict=%s θ=%.3f arm=%d mab_conf=%s",
        bio.verdict.value, bio.theta, arm, mab_conf.value,
    )

    return HoneypotResult(
        should_shadow    = True,
        synthetic_token  = token,
        verdict          = bio.verdict,
        confidence       = bio.confidence,
        mab_arm_selected = arm,
        mab_confidence   = mab_conf,
    )


def update_mab_reward(mab_agent, arm: int, reward: float) -> None:
    """
    Feed reward back to the MAB after a shadow session ends.
    arm=-1 (error/fallback path) is silently ignored.
    """
    if arm < 0:
        return
    try:
        mab_agent.update(arm, reward)
    except Exception as exc:
        logger.warning("[S2] MAB reward update failed for arm=%d: %s", arm, exc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _should_shadow(bio: BiometricResult) -> bool:
    if bio.verdict == HoneypotVerdict.BOT:
        return True
    if bio.verdict == HoneypotVerdict.SUSPECT and bio.confidence in (
        Confidence.HIGH, Confidence.MEDIUM
    ):
        return True
    return False


def _select_arm(mab_agent) -> tuple[int, Confidence]:
    """
    Ask the MAB for the best arm and derive a confidence from pull counts.
    Falls back to arm 0 if the MAB raises.
    """
    try:
        arm = mab_agent.select_arm()
        # Infer confidence from how many times this arm has been pulled
        pulls = int(getattr(mab_agent, "counts", [0] * 3)[arm])
        if pulls >= _MIN_ARM_PULLS:
            conf = Confidence.HIGH
        elif pulls > 0:
            conf = Confidence.MEDIUM
        else:
            conf = Confidence.LOW  # cold-start arm
        return arm, conf
    except Exception as exc:
        logger.warning("[S2] MAB select_arm failed (%s) — defaulting to arm 0", exc)
        return 0, Confidence.LOW


def _make_shadow_token(ip: str, arm: int, secret: str) -> str:
    """
    Synthetic session token that mimics the real token format.
    HMAC-signed with the shadow secret so it cannot be replayed against real endpoints.
    """
    payload = f"shadow:{ip}:{arm}:{int(time.time())}"
    sig     = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    encoded = (payload + ":" + sig).encode().hex()
    return secrets.token_urlsafe(8) + "." + encoded
