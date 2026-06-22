"""
attack_classifier.py — rule-based attacker-intent classification (Feature 2)
============================================================================

Sits between Stage 1 (biometric verdict) and Stage 2 (deception routing).
Converts raw request signals into an *intent* label so the deception engine can
pick the right synthetic environment:

    CREDENTIAL_STUFFING  → Banking shadow world (full "success" environment)
    BRUTE_FORCE          → Banking shadow world (tarpit-flavoured)
    RECON                → Shadow Admin (arm 3)
    SCRAPER              → Banking shadow world (read-heavy synthetic data)
    UNKNOWN              → default decoys (existing Stage 2 behaviour)

MVP scope: SIMPLE DETERMINISTIC RULES ONLY.  No ML, no training data.  The
rules are intentionally explainable so an analyst can audit every decision.
The ML upgrade path (LinUCB context, GBDT classifier) is documented but NOT
implemented here.

The classifier is pure and side-effect free: feed it an ``AttackSignals`` and
it returns an ``AttackClassification``.  It never raises on bad input — missing
signals simply lower confidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AttackClass(str, Enum):
    """Attacker intent categories supported by the MVP."""
    CREDENTIAL_STUFFING = "credential_stuffing"
    BRUTE_FORCE         = "brute_force"
    RECON               = "recon"
    SCRAPER             = "scraper"
    UNKNOWN             = "unknown"


class Confidence(str, Enum):
    """Local confidence band (mirrors backend.models.contracts.Confidence)."""
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


# Which deception strategy each class maps to.  This is the rule-based prior the
# Contextual Bandit (future work) would warm-start from.  "banking" and
# "shadow_admin" are world ids understood by shadow_world.ShadowWorldEngine.
DEFAULT_STRATEGY_FOR_CLASS = {
    AttackClass.CREDENTIAL_STUFFING: "banking",
    AttackClass.BRUTE_FORCE:         "banking",
    AttackClass.RECON:               "shadow_admin",
    AttackClass.SCRAPER:             "banking",
    AttackClass.UNKNOWN:             "banking",
}

# MAB arm hint per class (arm 3 = Shadow Admin).  Used only as a *hint*; the
# existing 3-arm MAB still owns DOM-decoy strategy selection.
ARM_HINT_FOR_CLASS = {
    AttackClass.CREDENTIAL_STUFFING: 1,   # Echo decoys
    AttackClass.BRUTE_FORCE:         0,   # Tarpit decoys
    AttackClass.RECON:               3,   # Shadow Admin
    AttackClass.SCRAPER:             2,   # Canary decoys
    AttackClass.UNKNOWN:            -1,
}


@dataclass
class AttackSignals:
    """
    Telemetry required by the MVP classifier.  Every field is optional so the
    classifier degrades gracefully when a signal is unavailable.

    Collect these in the /score handler from the request + recent history:

    distinct_usernames   number of distinct usernames seen from this client
    failed_attempts      consecutive failed auth attempts
    password_attempts    distinct passwords tried against ONE username
    request_rate         requests/second over the recent window
    admin_path_hits      hits on /admin, /wp-admin, /.env, /config, etc.
    unique_paths         number of distinct paths visited
    not_found_ratio      fraction of requests that 404'd (enumeration signal)
    theta                Stage-1 humanity score [0,1] (low = bot)
    user_agent           raw UA string (used for crawler heuristics)
    """
    distinct_usernames: int   = 0
    failed_attempts:    int   = 0
    password_attempts:  int   = 0
    request_rate:       float = 0.0
    admin_path_hits:    int   = 0
    unique_paths:       int   = 0
    not_found_ratio:    float = 0.0
    theta:              float = 1.0
    user_agent:         str   = ""


@dataclass
class AttackClassification:
    """Output of the classifier."""
    attack_class: AttackClass
    confidence:   Confidence
    reasons:      list[str]   = field(default_factory=list)
    # Convenience: pre-resolved routing hints so callers don't re-derive them.
    suggested_world: str      = "banking"
    arm_hint:        int      = -1

    def to_dict(self) -> dict:
        return {
            "attack_class":    self.attack_class.value,
            "confidence":      self.confidence.value,
            "reasons":         self.reasons,
            "suggested_world": self.suggested_world,
            "arm_hint":        self.arm_hint,
        }


# ── Thresholds (single source of truth — tune per deployment) ────────────────
_CRED_STUFFING_USERNAMES = 5    # many usernames, few passwords each
_BRUTE_FORCE_PASSWORDS   = 8    # one username, many passwords
_RECON_ADMIN_HITS        = 1    # any admin/config probe
_SCRAPER_REQ_RATE        = 8.0  # requests/second
_SCRAPER_UNIQUE_PATHS    = 25   # broad path sweep
_ENUM_NOT_FOUND_RATIO    = 0.5  # half the requests 404 → enumeration

_CRAWLER_UA_MARKERS = (
    "bot", "spider", "crawl", "scrapy", "python-requests", "curl",
    "wget", "httpclient", "headless", "phantom",
)


def classify(signals: AttackSignals) -> AttackClassification:
    """
    Classify attacker intent from request signals using simple rules.

    Rule precedence (first strong match wins, most specific first):
        1. RECON              — admin/config path probing or heavy 404 enum
        2. CREDENTIAL_STUFFING— many distinct usernames
        3. BRUTE_FORCE        — many password attempts on one username
        4. SCRAPER            — high request rate / broad path sweep / crawler UA
        5. UNKNOWN            — nothing matched
    """
    reasons: list[str] = []
    ua = (signals.user_agent or "").lower()

    # 1) RECON — looking for admin surfaces or enumerating endpoints.
    if signals.admin_path_hits >= _RECON_ADMIN_HITS:
        reasons.append(
            f"admin/config path probing (hits={signals.admin_path_hits})"
        )
        return _build(AttackClass.RECON, Confidence.HIGH, reasons)
    if signals.not_found_ratio >= _ENUM_NOT_FOUND_RATIO and signals.unique_paths >= 10:
        reasons.append(
            f"endpoint enumeration (404_ratio={signals.not_found_ratio:.2f}, "
            f"paths={signals.unique_paths})"
        )
        return _build(AttackClass.RECON, Confidence.MEDIUM, reasons)

    # 2) CREDENTIAL_STUFFING — spraying many accounts.
    if signals.distinct_usernames >= _CRED_STUFFING_USERNAMES:
        conf = Confidence.HIGH if signals.distinct_usernames >= 2 * _CRED_STUFFING_USERNAMES else Confidence.MEDIUM
        reasons.append(
            f"many distinct usernames ({signals.distinct_usernames})"
        )
        return _build(AttackClass.CREDENTIAL_STUFFING, conf, reasons)

    # 3) BRUTE_FORCE — hammering one account.
    if signals.password_attempts >= _BRUTE_FORCE_PASSWORDS or signals.failed_attempts >= _BRUTE_FORCE_PASSWORDS:
        reasons.append(
            f"repeated password attempts (pw={signals.password_attempts}, "
            f"fails={signals.failed_attempts})"
        )
        return _build(AttackClass.BRUTE_FORCE, Confidence.HIGH, reasons)

    # 4) SCRAPER — high volume / broad sweep / automated UA.
    crawler_ua = any(m in ua for m in _CRAWLER_UA_MARKERS)
    if signals.request_rate >= _SCRAPER_REQ_RATE:
        reasons.append(f"high request rate ({signals.request_rate:.1f}/s)")
        return _build(AttackClass.SCRAPER, Confidence.HIGH, reasons)
    if signals.unique_paths >= _SCRAPER_UNIQUE_PATHS:
        reasons.append(f"broad path sweep ({signals.unique_paths} paths)")
        return _build(AttackClass.SCRAPER, Confidence.MEDIUM, reasons)
    if crawler_ua:
        reasons.append("automated user-agent")
        # Low theta strengthens the call; high theta keeps it tentative.
        conf = Confidence.MEDIUM if signals.theta < 0.3 else Confidence.LOW
        return _build(AttackClass.SCRAPER, conf, reasons)

    # 5) UNKNOWN — bot detected upstream but intent unclear.
    reasons.append("no specific attack pattern matched")
    return _build(AttackClass.UNKNOWN, Confidence.LOW, reasons)


def _build(cls: AttackClass, conf: Confidence, reasons: list[str]) -> AttackClassification:
    return AttackClassification(
        attack_class    = cls,
        confidence      = conf,
        reasons         = reasons,
        suggested_world = DEFAULT_STRATEGY_FOR_CLASS[cls],
        arm_hint        = ARM_HINT_FOR_CLASS[cls],
    )
