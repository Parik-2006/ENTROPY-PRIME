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

import hashlib
import logging
import math
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any, Iterable, Optional

from .contracts import (
    BiometricContext,
    BiometricInput,
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

BEHAVIORAL_NUMERIC_FEATURES: tuple[str, ...] = (
    "keystroke_speed",
    "error_rate",
    "key_dwell_time",
    "inter_key_delay",
    "keystroke_consistency",
    "mouse_velocity",
    "mouse_acceleration",
    "click_interval",
    "scroll_speed",
    "activity_frequency",
    "session_duration",
    "hour_of_day",
    "day_of_week",
    "unique_ip_count",
    "device_change_frequency",
    "resource_sensitivity",
)

COMPONENT_FEATURES: dict[str, tuple[str, ...]] = {
    "keystroke": (
        "keystroke_speed",
        "error_rate",
        "key_dwell_time",
        "inter_key_delay",
        "keystroke_consistency",
    ),
    "mouse": (
        "mouse_velocity",
        "mouse_acceleration",
        "click_interval",
        "scroll_speed",
    ),
    "device": (
        "unique_ip_count",
        "device_change_frequency",
    ),
    "timing": (
        "hour_of_day",
        "day_of_week",
        "activity_frequency",
        "session_duration",
    ),
    "location": (
        "unique_ip_count",
    ),
    "context": (
        "resource_sensitivity",
    ),
}

DEFAULT_RISK_WEIGHTS: dict[str, float] = {
    "keystroke": 0.25,
    "device": 0.25,
    "timing": 0.20,
    "location": 0.15,
    "context": 0.15,
}


# ── Main entry point ──────────────────────────────────────────────────────────

def run(inp: ContextualBiometricInput | BiometricInput) -> BiometricResult:
    """
    Classify the incoming contextual signal.

    Never raises — unexpected values fall back to a LOW-confidence HUMAN so
    real users are never locked out by instrumentation noise.
    """
    if not isinstance(inp, ContextualBiometricInput):
        return run_legacy(inp)

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
    Backward-compatible threshold-only classifier for BiometricInput callers.

    The contextual path uses centroid distance and learning phase. Legacy
    callers historically used only theta, latent-vector presence, and
    server-load notes; keeping that behavior avoids surprising older pipeline
    tests and scripts.
    """
    theta = _clamp(float(getattr(raw, "theta", 0.5)))
    h_exp = _clamp(float(getattr(raw, "h_exp", 0.0)))
    server_load = _clamp(float(getattr(raw, "server_load", 0.0)))
    latent_vector = getattr(raw, "latent_vector", None)
    has_latent = isinstance(latent_vector, list) and len(latent_vector) == 32

    if theta <= BOT_THETA_HARD:
        verdict = HoneypotVerdict.BOT
        confidence = Confidence.HIGH
        is_bot = True
        is_suspect = False
    elif theta < BOT_THETA_SOFT:
        verdict = HoneypotVerdict.SUSPECT
        confidence = Confidence.MEDIUM if theta < 0.15 else Confidence.LOW
        is_bot = False
        is_suspect = True
    else:
        verdict = HoneypotVerdict.HUMAN
        is_bot = False
        is_suspect = False
        if theta >= 0.60:
            confidence = Confidence.HIGH
        elif theta >= 0.50:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW

    notes: list[str] = []
    if not has_latent:
        notes.append("no latent vector")
        if confidence == Confidence.HIGH:
            confidence = Confidence.MEDIUM
    if server_load > 0.85:
        notes.append(f"server_load={server_load:.2f}")

    return BiometricResult(
        theta=theta,
        h_exp=h_exp,
        server_load=server_load,
        verdict=verdict,
        confidence=confidence,
        is_bot=is_bot,
        is_suspect=is_suspect,
        note="; ".join(notes),
        context=None,
        centroid_dist=None,
    )


# ── Advanced behavioral profiling / anomaly analysis ─────────────────────

def build_behavioral_baseline(
    samples: Iterable[dict[str, Any]],
    *,
    user_id: str = "",
    baseline_days: int = 30,
    min_samples: int = 30,
) -> dict[str, Any]:
    """
    Build a statistical baseline from historical behavioral feature samples.

    The result is intentionally JSON-safe so it can be stored in MongoDB or
    Redis and consumed by the Stage 1 orchestration layer.
    """
    rows = [dict(sample or {}) for sample in samples]
    now = _utc_now()
    feature_stats: dict[str, dict[str, float]] = {}

    for feature in BEHAVIORAL_NUMERIC_FEATURES:
        values = [_as_float(row.get(feature)) for row in rows if row.get(feature) is not None]
        if not values:
            continue
        feature_stats[feature] = {
            "mean": mean(values),
            "std": max(pstdev(values), 1e-6) if len(values) > 1 else 1.0,
            "min": min(values),
            "max": max(values),
        }

    timestamps = [_parse_timestamp(row.get("timestamp")) for row in rows if row.get("timestamp")]
    timestamps = [ts for ts in timestamps if ts is not None]
    first_seen = min(timestamps).isoformat() if timestamps else now
    last_seen = max(timestamps).isoformat() if timestamps else now
    observed_days = _observed_days(timestamps)

    known_devices = sorted({
        str(row.get("device_id") or row.get("device_fingerprint") or "")
        for row in rows
        if row.get("device_id") or row.get("device_fingerprint")
    })
    known_ips = sorted({str(row.get("ip_address")) for row in rows if row.get("ip_address")})
    normal_hour_values: set[int] = set()
    weekend_count = 0
    for row in rows:
        hour = int(_as_float(row.get("hour_of_day"), -1))
        ts = _parse_timestamp(row.get("timestamp"))
        if not 0 <= hour <= 23 and ts is not None:
            hour = ts.hour
        if 0 <= hour <= 23:
            normal_hour_values.add(hour)
        is_weekend = bool(row.get("is_weekend"))
        if ts is not None:
            is_weekend = is_weekend or ts.weekday() >= 5
        if is_weekend:
            weekend_count += 1
    normal_hours = sorted(normal_hour_values)

    selected_features = list(feature_stats.keys())
    feature_vectors = [
        [_as_float(row.get(feature), feature_stats.get(feature, {}).get("mean", 0.0)) for feature in selected_features]
        for row in rows
    ]

    return {
        "user_id": user_id,
        "created_at": now,
        "updated_at": now,
        "baseline_days": max(observed_days, baseline_days if len(rows) >= min_samples else observed_days),
        "observed_days": observed_days,
        "sample_count": len(rows),
        "baseline_ready": len(rows) >= min_samples or observed_days >= baseline_days,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "feature_stats": feature_stats,
        "selected_features": selected_features,
        "feature_vectors": feature_vectors[-500:],
        "known_devices": known_devices,
        "known_ip_addresses": known_ips,
        "normal_hours": normal_hours,
        "weekend_activity_normal": bool(rows and weekend_count / len(rows) >= 0.25),
        "feature_importance": _feature_importance(feature_stats),
    }


def analyze_biometrics(
    features: dict[str, Any],
    baseline: Optional[dict[str, Any]] = None,
    *,
    history: Optional[Iterable[dict[str, Any]]] = None,
    anomaly_threshold: float = 0.70,
) -> dict[str, Any]:
    """
    Compare a current behavioral event against a user baseline.

    Uses z-score/statistical detection by default and blends in an Isolation
    Forest score when sklearn is installed and the baseline has vectors.
    """
    baseline = baseline or {}
    history_rows = [dict(row or {}) for row in (history or [])]
    feature_stats: dict[str, dict[str, float]] = baseline.get("feature_stats", {}) or {}

    zscores: dict[str, float] = {}
    feature_scores: dict[str, float] = {}
    for feature, stats in feature_stats.items():
        value = _as_float(features.get(feature), stats.get("mean", 0.0))
        std = max(_as_float(stats.get("std"), 1.0), 1e-6)
        z = abs((value - _as_float(stats.get("mean"), 0.0)) / std)
        zscores[feature] = round(z, 4)
        feature_scores[feature] = _score_from_z(z)

    component_scores = {
        component: _component_score(feature_scores, names)
        for component, names in COMPONENT_FEATURES.items()
    }
    _apply_contextual_component_rules(features, baseline, component_scores)

    isolation_score = _isolation_forest_score(features, baseline)
    statistical_score = max(component_scores.values(), default=0.0)
    anomaly_score = (
        max(statistical_score, isolation_score)
        if isolation_score is not None
        else statistical_score
    )
    anomaly_flags = _anomaly_flags(features, baseline, component_scores, zscores)
    trend = _risk_trend(history_rows)
    confidence = _analysis_confidence(baseline, component_scores, isolation_score)

    return {
        "user_id": features.get("user_id") or baseline.get("user_id", ""),
        "anomaly_score": round(_clamp(anomaly_score), 4),
        "confidence": round(_clamp(confidence), 4),
        "anomaly_flags": anomaly_flags,
        "component_scores": {k: round(_clamp(v), 4) for k, v in component_scores.items()},
        "historical_baseline": baseline,
        "feature_zscores": zscores,
        "isolation_forest_score": None if isolation_score is None else round(isolation_score, 4),
        "trend": trend,
        "is_anomalous": anomaly_score >= anomaly_threshold,
    }


def calculate_behavioral_risk(
    analysis: dict[str, Any],
    *,
    weights: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    """Convert anomaly analysis into the Stage 1 behavioral risk structure."""
    weights = weights or DEFAULT_RISK_WEIGHTS
    components = analysis.get("component_scores", {}) or {}
    weighted_sum = 0.0
    total_weight = 0.0
    for component, weight in weights.items():
        weighted_sum += _as_float(components.get(component), 0.0) * weight
        total_weight += weight
    risk_score = weighted_sum / total_weight if total_weight else _as_float(analysis.get("anomaly_score"))
    risk_score = _clamp(max(risk_score, _as_float(analysis.get("anomaly_score")) * 0.75))
    confidence = _clamp(_as_float(analysis.get("confidence"), 0.5))

    if risk_score >= 0.80:
        risk_level = "critical"
    elif risk_score >= 0.65:
        risk_level = "high"
    elif risk_score >= 0.35:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "risk_score": round(risk_score, 4),
        "confidence": round(confidence, 4),
        "risk_level": risk_level,
        "component_breakdown": {k: round(_clamp(v), 4) for k, v in components.items()},
        "trend": analysis.get("trend", "stable"),
        "supporting_evidence": list(analysis.get("anomaly_flags", [])),
    }


def calculate_risk_score(analysis: dict[str, Any]) -> dict[str, Any]:
    """Alias used by the Stage 1 orchestration spec."""
    return calculate_behavioral_risk(analysis)


def prepare_stage2_input(
    analysis: dict[str, Any],
    risk: dict[str, Any],
    *,
    user_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Create the downstream Stage 2 payload described by the PARIK spec."""
    return {
        "biometric_score": risk["risk_score"],
        "anomaly_flags": analysis.get("anomaly_flags", []),
        "user_profile": user_profile or {},
        "confidence": risk["confidence"],
        "risk_level": risk["risk_level"],
        "stage1_data": {
            "component_scores": analysis.get("component_scores", {}),
            "trend": risk.get("trend", "stable"),
            "is_anomalous": analysis.get("is_anomalous", False),
        },
    }


def _component_score(feature_scores: dict[str, float], features: Iterable[str]) -> float:
    values = [feature_scores[name] for name in features if name in feature_scores]
    return max(values) if values else 0.0


def _apply_contextual_component_rules(
    features: dict[str, Any],
    baseline: dict[str, Any],
    component_scores: dict[str, float],
) -> None:
    device = str(features.get("device_id") or features.get("device_fingerprint") or "")
    known_devices = set(baseline.get("known_devices", []) or [])
    if device and known_devices and device not in known_devices:
        component_scores["device"] = max(component_scores.get("device", 0.0), 0.95)

    ip_address = str(features.get("ip_address") or "")
    known_ips = set(baseline.get("known_ip_addresses", []) or [])
    if ip_address and known_ips and ip_address not in known_ips:
        component_scores["location"] = max(component_scores.get("location", 0.0), 0.75)

    hour = int(_as_float(features.get("hour_of_day"), -1))
    normal_hours = set(int(h) for h in baseline.get("normal_hours", []) or [])
    if hour >= 0 and normal_hours and hour not in normal_hours:
        off_hour_score = 0.85 if hour < 6 or hour > 22 else 0.65
        component_scores["timing"] = max(component_scores.get("timing", 0.0), off_hour_score)

    if bool(features.get("is_weekend")) and not bool(baseline.get("weekend_activity_normal", False)):
        component_scores["timing"] = max(component_scores.get("timing", 0.0), 0.65)

    if _as_float(features.get("resource_sensitivity"), 0.0) >= 0.8:
        component_scores["context"] = max(component_scores.get("context", 0.0), 0.70)


def _anomaly_flags(
    features: dict[str, Any],
    baseline: dict[str, Any],
    component_scores: dict[str, float],
    zscores: dict[str, float],
) -> list[str]:
    flags: list[str] = []
    for feature, z in zscores.items():
        if z >= 3.0:
            flags.append(f"{feature}_unusual")

    if component_scores.get("keystroke", 0.0) >= 0.70:
        flags.append("keystroke_pattern_unusual")
    if component_scores.get("mouse", 0.0) >= 0.70:
        flags.append("mouse_pattern_unusual")
    if component_scores.get("device", 0.0) >= 0.80:
        flags.append("new_device")
    if component_scores.get("location", 0.0) >= 0.70:
        flags.append("location_unusual")
    if component_scores.get("timing", 0.0) >= 0.70:
        flags.append("off_hours_access")
    if component_scores.get("context", 0.0) >= 0.70:
        flags.append("sensitive_context")

    device = str(features.get("device_id") or features.get("device_fingerprint") or "")
    if device and device not in set(baseline.get("known_devices", []) or []):
        flags.append("unknown_device")

    return sorted(set(flags))


def _isolation_forest_score(features: dict[str, Any], baseline: dict[str, Any]) -> Optional[float]:
    selected = baseline.get("selected_features", []) or []
    vectors = baseline.get("feature_vectors", []) or []
    if len(selected) < 2 or len(vectors) < 8:
        return None
    try:
        from sklearn.ensemble import IsolationForest  # type: ignore
    except Exception:
        return None

    try:
        model = IsolationForest(contamination="auto", random_state=7)
        model.fit(vectors)
        current = [[_as_float(features.get(name), 0.0) for name in selected]]
        raw = float(model.decision_function(current)[0])
        # decision_function is positive for normal points and lower for outliers.
        return _clamp(0.5 - raw)
    except Exception as exc:
        logger.debug("[S1] IsolationForest skipped: %s", exc)
        return None


def _analysis_confidence(
    baseline: dict[str, Any],
    component_scores: dict[str, float],
    isolation_score: Optional[float],
) -> float:
    samples = int(_as_float(baseline.get("sample_count"), 0.0))
    sample_conf = min(0.35, samples / 120.0)
    method_conf = 0.15 if isolation_score is not None else 0.0
    signal_conf = min(0.25, max(component_scores.values(), default=0.0) * 0.25)
    return 0.40 + sample_conf + method_conf + signal_conf


def _risk_trend(history: list[dict[str, Any]]) -> str:
    if len(history) < 3:
        return "stable"
    scores = [
        _as_float(row.get("risk_score", row.get("anomaly_score")), 0.0)
        for row in history[-5:]
    ]
    if len(scores) < 3:
        return "stable"
    delta = scores[-1] - scores[0]
    if delta > 0.15:
        return "increasing"
    if delta < -0.15:
        return "decreasing"
    return "stable"


def _feature_importance(feature_stats: dict[str, dict[str, float]]) -> dict[str, float]:
    if not feature_stats:
        return {}
    spreads = {
        name: max(_as_float(stats.get("std"), 0.0), 1e-6)
        for name, stats in feature_stats.items()
    }
    total = sum(spreads.values()) or 1.0
    return {name: round(value / total, 4) for name, value in spreads.items()}


def _score_from_z(z: float) -> float:
    if z <= 1.0:
        return 0.0
    return _clamp((z - 1.0) / 3.0)


def _observed_days(timestamps: list[datetime]) -> int:
    if not timestamps:
        return 0
    return max(1, (max(timestamps).date() - min(timestamps).date()).days + 1)


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def typing_pattern_hash(intervals: Iterable[Any]) -> str:
    """Stable privacy-preserving hash for a sequence of timing intervals."""
    rounded = ",".join(str(round(_as_float(item), 2)) for item in intervals)
    return hashlib.sha256(rounded.encode("utf-8")).hexdigest()[:24]
