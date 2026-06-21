"""
backend/services/biometric_compare.py — Phase D.1 (SHADOW MODE / validation only)

Pure, side-effect-free comparison of a *current* behavioral feature window against
a *frozen* enrollment baseline. Produces distance, similarity, and confidence.

IMPORTANT — this module makes NO authentication decision and influences nothing:
not PPO, not the watchdog, not the trust score, not the UI confidence, not
re-authentication. Its output is logged for validation only. It is intentionally
dependency-free and deterministic so it can be unit-tested in isolation.

The distance math mirrors the existing client drift formula
(src/services/biometrics.js:143-150) so the server and client agree, but here it
is weighted by per-feature discriminability and computed server-side.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence

EPS = 1e-6

# Distance thresholds in standardized (std) units — mirror the design doc and the
# live UI tiers. Used only to derive a *logged* confidence value in shadow mode.
WARN_D      = 1.0
CHALLENGE_D = 1.5
BLOCK_D     = 2.5


def standardized_distance(
    window: Sequence[float],
    mean: Sequence[float],
    std: Sequence[float],
    weights: Optional[Sequence[float]] = None,
) -> float:
    """Weighted standardized (z-score) distance:  sqrt( Σ wᵢ·zᵢ² / Σ wᵢ )."""
    n = min(len(window), len(mean), len(std))
    if n == 0:
        return 0.0
    num = 0.0
    wsum = 0.0
    for i in range(n):
        s = std[i] if (std[i] and std[i] > EPS) else 0.1
        z = (window[i] - mean[i]) / (s + EPS)
        w = weights[i] if (weights and i < len(weights)) else 1.0
        num += w * z * z
        wsum += w
    if wsum <= 0:
        return 0.0
    return math.sqrt(num / wsum)


def similarity_from_distance(d: float) -> float:
    """Gaussian similarity in (0, 1].  1.0 = identical, → 0 = far apart."""
    return math.exp(-(d * d) / 2.0)


def confidence_from_distance(d: float) -> int:
    """Piecewise distance → confidence (0–100), matching the live tier bands."""
    if d <= WARN_D:
        c = 100 - (d / WARN_D) * 15                                   # 100 → 85
    elif d <= CHALLENGE_D:
        c = 85 - ((d - WARN_D) / (CHALLENGE_D - WARN_D)) * 20         # 85 → 65
    elif d <= BLOCK_D:
        c = 65 - ((d - CHALLENGE_D) / (BLOCK_D - CHALLENGE_D)) * 25   # 65 → 40
    else:
        c = max(5.0, 40 - (d - BLOCK_D) * 9)                          # 40 → 5
    return int(round(max(0.0, min(100.0, c))))


def tier_for(conf: int) -> str:
    if conf >= 85:
        return "green"
    if conf >= 65:
        return "yellow"
    if conf >= 40:
        return "orange"
    return "red"


def compare(window: Sequence[float], baseline: dict) -> dict:
    """
    Compare a current feature window against a frozen baseline document
    (as returned by database.get_enrollment_baseline).

    Returns a JSON-safe dict — never raises on well-formed numeric input.
    """
    mean    = baseline.get("mean") or []
    std     = baseline.get("std") or []
    weights = baseline.get("feature_weights")
    order   = baseline.get("feature_order") or []

    d   = standardized_distance(window, mean, std, weights)
    sim = similarity_from_distance(d)
    conf = confidence_from_distance(d)

    per_feature: List[dict] = []
    n = min(len(window), len(mean), len(std))
    for i in range(n):
        s = std[i] if (std[i] and std[i] > EPS) else 0.1
        z = (window[i] - mean[i]) / (s + EPS)
        per_feature.append({
            "feature": order[i] if i < len(order) else f"f{i}",
            "z":       round(z, 3),
            "window":  round(float(window[i]), 4),
            "mean":    round(float(mean[i]), 4),
        })

    return {
        "distance":          round(d, 4),
        "similarity":        round(sim, 4),
        "confidence":        conf,
        "tier":              tier_for(conf),
        "baseline_version":  baseline.get("baseline_version", 1),
        "n_features":        n,
        "per_feature":       per_feature,
    }
