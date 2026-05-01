"""
Stage 2 — Honeypot Classifier
Consumes BiometricResult. If bot/suspect, uses MAB to pick a deception arm
and issues a synthetic shadow token. Otherwise passes through.

Input contract:  BiometricResult
Output contract: HoneypotResult
"""
from __future__ import annotations
import hashlib, hmac, secrets, time
from typing import Optional

from .contracts import (
    BiometricResult, HoneypotResult,
    Confidence, HoneypotVerdict,
    BOT_THETA_HARD, BOT_THETA_SOFT,
)


# ── Deception arms (MAB arms map to these) ────────────────────────────────────
DECEPTION_ARMS = [
    "fake_data_feed",       # arm 0: serve plausible fake JSON responses
    "slow_drip",            # arm 1: add artificial latency + partial data
    "canary_token_inject",  # arm 2: embed trackable canary tokens in responses
]


def run(
    bio: BiometricResult,
    mab_agent,              # MABAgent instance (may be None → fallback)
    shadow_secret: str,
    ip_address: str = "?",
) -> HoneypotResult:
    """
    Routing logic:
      BOT    (conf HIGH/MEDIUM) → shadow immediately
      BOT    (conf LOW)         → shadow with LOW confidence flag
      SUSPECT (conf HIGH)       → shadow with MEDIUM confidence
      SUSPECT (conf MEDIUM/LOW) → pass through (benefit of doubt)
      HUMAN                     → pass through

    MAB fallback: if mab_agent is None or raises, arm 0 is used and
    mab_confidence is set to LOW.
    """
    should_shadow = _routing_decision(bio)

    if not should_shadow:
        return HoneypotResult(
            should_shadow    = False,
            synthetic_token  = None,
            verdict          = bio.verdict,
            confidence       = bio.confidence,
            mab_arm_selected = -1,
            mab_confidence   = Confidence.LOW,
        )

    # ── MAB: pick deception arm ───────────────────────────────────────────────
    arm, mab_conf = _select_arm(mab_agent)

    token = _make_synthetic_token(shadow_secret, ip_address, arm)

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
    Called after a shadow session ends to give the MAB its reward signal.
    Safe to call with mab_agent=None (no-op).
    """
    if mab_agent is None or arm < 0:
        return
    try:
        mab_agent.update(arm, reward)
    except Exception:
        pass


# ── Internals ─────────────────────────────────────────────────────────────────

def _routing_decision(bio: BiometricResult) -> bool:
    if bio.verdict == HoneypotVerdict.BOT:
        # Shadow all bots regardless of confidence
        return True
    if bio.verdict == HoneypotVerdict.SUSPECT and bio.confidence == Confidence.HIGH:
        # High-confidence suspect → shadow
        return True
    return False


def _select_arm(mab_agent) -> tuple[int, Confidence]:
    if mab_agent is None:
        return 0, Confidence.LOW
    try:
        arm = int(mab_agent.select_arm())
        # Reflect MAB's own certainty: if counts are low, it's guessing
        counts = mab_agent.counts
        if counts[arm] < 10:
            conf = Confidence.LOW
        elif counts[arm] < 50:
            conf = Confidence.MEDIUM
        else:
            conf = Confidence.HIGH
        return arm, conf
    except Exception:
        return 0, Confidence.LOW


def _make_synthetic_token(secret: str, ip: str, arm: int) -> str:
    payload = f"shadow:{ip}:{arm}:{time.time():.3f}"
    sig     = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"ep_shadow_{secrets.token_urlsafe(32)}.{sig[:16]}"
