"""
pipeline/stage2_honeypot.py  —  Stage 2: Honeypot Classification  v2.0
======================================================================

Changes in v2.0
───────────────
• Each MAB arm now emits a signed `ChallengeConfig` describing DOM decoys
  for the client SDK to inject.  Bots that interact with any decoy fire a
  /honeypot/trigger hit, which feeds back into the MAB reward loop.

• `DecoySpec` carries enough info for the SDK to render an invisible-but-
  plausible DOM element.  Each spec is fingerprinted with a per-request nonce
  so triggered events can be traced back to the originating challenge.

• `ChallengeConfig` is HMAC-signed (SHA-256, shadow_secret) so the backend
  can validate inbound /honeypot/trigger payloads without a DB lookup.
  The signature covers: challenge_id + arm + expires_at + every decoy_id,
  joined with "|".  Changing any field invalidates the signature.

Arm → decoy strategy mapping
─────────────────────────────
  Arm 0  Tarpit   — Heavy form decoys.  Fake email/phone/password inputs +
                    submit button.  Autocomplete bots and form-fillers reliably
                    interact with these.  Slow response variant (handled in SDK).
  Arm 1  Echo     — Mirror decoys.  Field names closely resemble real form
                    fields (slight mutations: "usernmae", "passwrd").  Targets
                    DOM-scraping bots that clone field sets.  Includes a fake
                    "Forgot password?" link.
  Arm 2  Canary   — Silent audit.  Single invisible input + invisible anchor.
                    Minimal DOM footprint.  Targets aggressive crawlers that
                    follow all links / fill all fields; logs everything silently
                    without altering response latency.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

from .contracts import (
    BiometricResult,
    Confidence,
    HoneypotResult,
    HoneypotVerdict,
)

logger = logging.getLogger("entropy_prime.stage2")

_MIN_ARM_PULLS  = 10   # pulls below this → MAB confidence LOW
_CHALLENGE_TTL  = 120  # seconds before a challenge expires


# ─────────────────────────────────────────────────────────────────────────────
# Decoy / Challenge domain objects
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DecoySpec:
    """
    Descriptor for a single invisible DOM decoy element.

    The SDK receives this and renders an element that:
      • Is visually invisible to humans (off-canvas, opacity-0, aria-hidden)
      • Has realistic HTML attributes bots scan for
      • Fires a /honeypot/trigger report on any interaction

    Fields
    ──────
    decoy_id    Unique nonce per request — traces which decoy was triggered.
    kind        Element kind the SDK renders: "input" | "button" | "link" | "checkbox"
    name        HTML name= / id= attribute (must look realistic to fool bots)
    label       Human-readable label text (screen-reader hidden; bots may parse it)
    autocomplete  HTML autocomplete= hint — e.g. "email", "current-password"
    tab_index   Always -1 (keyboard-unreachable for humans; bots ignore this)
    """
    decoy_id:     str
    kind:         str   # "input" | "button" | "link" | "checkbox"
    name:         str
    label:        str
    autocomplete: str  = ""
    tab_index:    int  = -1


@dataclass
class ChallengeConfig:
    """
    Signed challenge payload sent inside the /score response.

    The SDK uses `decoys` to inject invisible DOM traps and `expires_at` to
    schedule self-destruction.  `signature` lets the backend verify the payload
    on /honeypot/trigger without a DB round-trip.

    Fields
    ──────
    challenge_id   Per-request UUID — used in trigger reports and signing.
    arm            MAB arm that selected this challenge (0/1/2).
    decoys         Ordered list of DecoySpec descriptors for the SDK.
    expires_at     Unix timestamp; SDK stops monitoring after this.
    signature      HMAC-SHA256 over (challenge_id|arm|expires_at|decoy_ids).
    """
    challenge_id: str
    arm:          int
    decoys:       list[DecoySpec]
    expires_at:   float
    signature:    str

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict for the /score response body."""
        return {
            "challenge_id": self.challenge_id,
            "arm":          self.arm,
            "expires_at":   self.expires_at,
            "signature":    self.signature,
            "decoys": [
                {
                    "decoy_id":     d.decoy_id,
                    "kind":         d.kind,
                    "name":         d.name,
                    "label":        d.label,
                    "autocomplete": d.autocomplete,
                    "tab_index":    d.tab_index,
                }
                for d in self.decoys
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run(
    bio:           BiometricResult,
    mab_agent,
    shadow_secret: str,
    ip_address:    str = "?",
) -> HoneypotResult:
    """
    Decide shadow routing and, if shadowing, build a signed ChallengeConfig.

    Shadow routing triggers when:
      • verdict == BOT   (always)
      • verdict == SUSPECT  AND  confidence in {HIGH, MEDIUM}

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
            mab_confidence   = Confidence.HIGH,
            challenge        = None,
        )

    # ── Select MAB arm ────────────────────────────────────────────────────────
    arm, mab_conf = _select_arm(mab_agent)

    # ── Generate synthetic shadow token ───────────────────────────────────────
    token = _make_shadow_token(ip_address, arm, shadow_secret)

    # ── Build signed challenge config for the SDK ─────────────────────────────
    challenge = _build_challenge(arm, shadow_secret)

    logger.info(
        "[S2] Shadow routing: verdict=%s arm=%d mab_conf=%s challenge=%s",
        bio.verdict.value, arm, mab_conf.value, challenge.challenge_id,
    )

    return HoneypotResult(
        should_shadow    = True,
        synthetic_token  = token,
        verdict          = bio.verdict,
        confidence       = bio.confidence,
        mab_arm_selected = arm,
        mab_confidence   = mab_conf,
        challenge        = challenge,
    )


def verify_challenge_signature(
    challenge_id: str,
    arm:          int,
    expires_at:   float,
    decoy_ids:    list[str],
    signature:    str,
    shadow_secret: str,
) -> bool:
    """
    Validate a challenge signature on inbound /honeypot/trigger.

    Returns True iff:
      • The HMAC matches (payload not tampered with)
      • The challenge has not expired

    Call this in the /honeypot/trigger route handler before logging the hit
    or updating the MAB reward.
    """
    if time.time() > expires_at:
        return False  # expired challenge

    expected = _sign_challenge(challenge_id, arm, expires_at, decoy_ids, shadow_secret)
    return secrets.compare_digest(expected, signature)


def update_mab_reward(mab_agent, arm: int, reward: float) -> None:
    """
    Feed reward back to the MAB after a shadow session ends.
    arm=-1 (error / fallback path) is silently ignored.
    """
    if arm < 0:
        return
    try:
        mab_agent.update(arm, reward)
    except Exception as exc:
        logger.warning("[S2] MAB reward update failed for arm=%d: %s", arm, exc)


# ─────────────────────────────────────────────────────────────────────────────
# Arm strategies — decoy specs per arm
# ─────────────────────────────────────────────────────────────────────────────

def _arm0_tarpit_decoys() -> list[DecoySpec]:
    """
    Arm 0 — Tarpit: heavy form-fill bait.

    Four realistic form fields + a submit button.  Autocomplete bots and
    credential-stuffing scrapers that auto-fill forms will reliably touch these.
    The SDK additionally slows down responses for this arm to amplify the tarpit
    effect (configurable via the `arm` field in ChallengeConfig).
    """
    return [
        DecoySpec(
            decoy_id     = _nonce(),
            kind         = "input",
            name         = "ep_email_verify",
            label        = "Verify Email",
            autocomplete = "email",
        ),
        DecoySpec(
            decoy_id     = _nonce(),
            kind         = "input",
            name         = "ep_phone_confirm",
            label        = "Phone Confirmation",
            autocomplete = "tel",
        ),
        DecoySpec(
            decoy_id     = _nonce(),
            kind         = "input",
            name         = "ep_password_hint",
            label        = "Password Hint",
            autocomplete = "current-password",
        ),
        DecoySpec(
            decoy_id     = _nonce(),
            kind         = "button",
            name         = "ep_submit_verify",
            label        = "Verify Account",
        ),
    ]


def _arm1_echo_decoys() -> list[DecoySpec]:
    """
    Arm 1 — Echo: mirror / mutated field decoys.

    Field names are slightly mutated versions of common form fields.
    DOM-scraping bots that clone field sets or match on partial name patterns
    will interact with these.  Includes a fake "Forgot password?" link — a
    classic canary for session-harvesting crawlers.
    """
    return [
        DecoySpec(
            decoy_id     = _nonce(),
            kind         = "input",
            name         = "usernmae",            # typo mutation of "username"
            label        = "Username",
            autocomplete = "username",
        ),
        DecoySpec(
            decoy_id     = _nonce(),
            kind         = "input",
            name         = "passwrd",             # typo mutation of "password"
            label        = "Password",
            autocomplete = "current-password",
        ),
        DecoySpec(
            decoy_id     = _nonce(),
            kind         = "checkbox",
            name         = "ep_rememberme",
            label        = "Keep me signed in",
        ),
        DecoySpec(
            decoy_id     = _nonce(),
            kind         = "link",
            name         = "ep_forgot_pw",
            label        = "Forgot password?",
        ),
    ]


def _arm2_canary_decoys() -> list[DecoySpec]:
    """
    Arm 2 — Canary: silent minimal audit.

    A single invisible input and anchor.  Minimal DOM footprint reduces the
    chance the decoys are detected by sophisticated bots, while still catching
    aggressive crawlers that follow all links or fill all inputs.  No latency
    impact — fastest arm for the MAB to learn on.
    """
    return [
        DecoySpec(
            decoy_id     = _nonce(),
            kind         = "input",
            name         = "ep_canary_field",
            label        = "Security Token",
            autocomplete = "off",
        ),
        DecoySpec(
            decoy_id     = _nonce(),
            kind         = "link",
            name         = "ep_canary_link",
            label        = "Terms of Service",
        ),
    ]


_ARM_STRATEGIES = {
    0: _arm0_tarpit_decoys,
    1: _arm1_echo_decoys,
    2: _arm2_canary_decoys,
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _should_shadow(bio: BiometricResult) -> bool:
    if bio.verdict == HoneypotVerdict.BOT:
        return True
    if bio.verdict == HoneypotVerdict.SUSPECT and bio.confidence in (
        Confidence.HIGH, Confidence.MEDIUM
    ):
        return True
    return False


def _select_arm(mab_agent) -> tuple[int, Confidence]:
    try:
        arm   = mab_agent.select_arm()
        pulls = int(getattr(mab_agent, "counts", [0] * 3)[arm])
        if pulls >= _MIN_ARM_PULLS:
            conf = Confidence.HIGH
        elif pulls > 0:
            conf = Confidence.MEDIUM
        else:
            conf = Confidence.LOW
        return arm, conf
    except Exception as exc:
        logger.warning("[S2] MAB select_arm failed (%s) — defaulting to arm 0", exc)
        return 0, Confidence.LOW


def _nonce(length: int = 8) -> str:
    """Short URL-safe nonce for decoy fingerprinting."""
    return secrets.token_urlsafe(length)


def _sign_challenge(
    challenge_id: str,
    arm:          int,
    expires_at:   float,
    decoy_ids:    list[str],
    secret:       str,
) -> str:
    payload = "|".join([challenge_id, str(arm), str(int(expires_at))] + decoy_ids)
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _build_challenge(arm: int, shadow_secret: str) -> ChallengeConfig:
    challenge_id = secrets.token_urlsafe(16)
    expires_at   = time.time() + _CHALLENGE_TTL
    decoys       = _ARM_STRATEGIES.get(arm, _arm2_canary_decoys)()
    decoy_ids    = [d.decoy_id for d in decoys]
    signature    = _sign_challenge(challenge_id, arm, expires_at, decoy_ids, shadow_secret)

    return ChallengeConfig(
        challenge_id = challenge_id,
        arm          = arm,
        decoys       = decoys,
        expires_at   = expires_at,
        signature    = signature,
    )


def _make_shadow_token(ip: str, arm: int, secret: str) -> str:
    """
    Synthetic session token that mimics the real token format.
    HMAC-signed with the shadow secret; prefixed "ep_shadow_" for internal
    identification without being obvious to external observers.
    """
    import time as _time
    payload = f"shadow:{ip}:{arm}:{int(_time.time())}"
    sig     = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    encoded = (payload + ":" + sig).encode().hex()
    return "ep_shadow_" + secrets.token_hex(4) + "." + encoded