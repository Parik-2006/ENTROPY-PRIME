"""Stage 1 biometric orchestration and legacy model re-exports."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from ..models.stage1_biometric import (
        analyze_biometrics as _analyze_biometrics,
        calculate_risk_score as _calculate_risk_score,
        prepare_stage2_input as _prepare_stage2_input,
        run,
        run_legacy,
    )
    from ..services.biometric_services import (
        analyze_user_event,
        extract_biometric_features,
        get_baseline,
        get_profile_history,
        load_user_profile,
        log_anomaly,
    )
    from ..services.redis_client import redis_set
except ImportError:
    from models.stage1_biometric import (  # type: ignore
        analyze_biometrics as _analyze_biometrics,
        calculate_risk_score as _calculate_risk_score,
        prepare_stage2_input as _prepare_stage2_input,
        run,
        run_legacy,
    )

    analyze_user_event = None
    extract_biometric_features = None
    get_baseline = None
    get_profile_history = None
    load_user_profile = None
    log_anomaly = None

    async def redis_set(*args, **kwargs):  # type: ignore
        return False

logger = logging.getLogger("entropy_prime.stage1.pipeline")


async def receive_biometric_event(raw_event: dict[str, Any], db: Any = None) -> dict[str, Any]:
    """
    Full PARIK Stage 1 flow: event -> features -> profile/baseline -> risk.

    Returns the Stage 2-ready envelope described in PARIK_STAGE1_BIOMETRIC.md.
    """
    user_id = str(raw_event.get("user_id") or raw_event.get("userId") or "")
    if not user_id:
        raise ValueError("user_id is required for Stage 1 biometric analysis")
    if analyze_user_event is None:
        raise RuntimeError("Stage 1 service layer is unavailable in this import mode")

    result = await analyze_user_event(user_id, raw_event, db=db)
    analysis = result["analysis"]
    risk = result["risk"]
    baseline = result["baseline"]
    profile = result["profile"]
    analysis_id = str(uuid.uuid4())

    output = {
        "stage": 1,
        "analysis_id": analysis_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "biometric_score": risk["risk_score"],
        "confidence": risk["confidence"],
        "risk_level": risk["risk_level"],
        "anomaly_flags": analysis.get("anomaly_flags", []),
        "baseline_ready": bool(baseline.get("baseline_ready")),
        "baseline_days": int(baseline.get("baseline_days", 0) or 0),
        "user_profile": profile,
        "stage2_input": result["stage2_input"],
    }
    await send_to_redis_cache(f"stage1:analysis:{analysis_id}", output, ttl_seconds=3600)
    return output


def extract_features(raw_event: dict[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper for feature extraction."""
    if extract_biometric_features is None:
        raise RuntimeError("Stage 1 service layer is unavailable in this import mode")
    return extract_biometric_features(raw_event)


async def load_or_create_user_profile(user_id: str, db: Any = None) -> dict[str, Any]:
    """Load an existing profile or return a new transient profile shell."""
    if load_user_profile is None:
        raise RuntimeError("Stage 1 service layer is unavailable in this import mode")
    profile = await load_user_profile(user_id, db=db)
    if profile:
        return profile
    return {
        "user_id": user_id,
        "profile": {},
        "baseline_days": 0,
        "baseline_ready": False,
        "last_activity": None,
        "profile_version": 0,
        "cached": False,
    }


async def check_baseline_ready(user_id: str, db: Any = None) -> bool:
    """Return whether a user's Stage 1 baseline is ready."""
    if get_baseline is None:
        raise RuntimeError("Stage 1 service layer is unavailable in this import mode")
    baseline = await get_baseline(user_id, db=db)
    return bool(baseline and baseline.get("baseline_ready"))


def analyze_biometrics(
    features: dict[str, Any],
    profile_or_baseline: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run model-level anomaly analysis from extracted features."""
    baseline = profile_or_baseline or {}
    if "feature_stats" not in baseline and isinstance(baseline.get("baseline"), dict):
        baseline = baseline["baseline"]
    return _analyze_biometrics(features, baseline, history=history)


def calculate_risk_score(analysis: dict[str, Any]) -> dict[str, Any]:
    """Run model-level behavioral risk scoring."""
    return _calculate_risk_score(analysis)


def generate_stage2_input(
    analysis: dict[str, Any],
    risk: dict[str, Any],
    user_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the downstream Stage 2 JSON payload."""
    return _prepare_stage2_input(analysis, risk, user_profile=user_profile)


async def aggregate_user_activities(
    user_id: str,
    time_window: timedelta | int | float = timedelta(days=30),
    db: Any = None,
) -> dict[str, Any]:
    """Aggregate recent user activity for retraining/baseline inspection."""
    if get_profile_history is None:
        raise RuntimeError("Stage 1 service layer is unavailable in this import mode")
    if isinstance(time_window, (int, float)):
        time_window = timedelta(seconds=float(time_window))
    cutoff = datetime.now(timezone.utc) - time_window
    rows = await get_profile_history(user_id, limit=1000, db=db)
    recent = [
        row for row in rows
        if _parse_timestamp(row.get("timestamp")) is None
        or _parse_timestamp(row.get("timestamp")) >= cutoff
    ]
    return {
        "user_id": user_id,
        "time_window_seconds": int(time_window.total_seconds()),
        "event_count": len(recent),
        "activities": recent,
    }


def detect_anomalies(current_data: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper around model anomaly detection."""
    return _analyze_biometrics(current_data, baseline)


def calculate_overall_risk(anomalies: dict[str, Any]) -> float:
    """Return just the numeric risk score for callers that need a scalar."""
    return float(_calculate_risk_score(anomalies)["risk_score"])


def prepare_stage2_input(
    analysis: dict[str, Any],
    risk: dict[str, Any],
    user_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper matching the markdown function name."""
    return generate_stage2_input(analysis, risk, user_profile)


async def log_analysis(
    user_id: str,
    analysis: dict[str, Any],
    risk: dict[str, Any],
    db: Any = None,
) -> None:
    """Persist an analysis only when it is anomalous."""
    if log_anomaly is None:
        raise RuntimeError("Stage 1 service layer is unavailable in this import mode")
    if analysis.get("is_anomalous"):
        await log_anomaly(user_id, analysis, risk, db=db)


async def log_to_database(
    user_id: str,
    analysis: dict[str, Any],
    risk: dict[str, Any],
    db: Any = None,
) -> None:
    """Alias requested by the PARIK spec."""
    await log_analysis(user_id, analysis, risk, db=db)


async def send_to_redis_cache(key: str, data: dict[str, Any], ttl_seconds: int = 3600) -> bool:
    """Cache Stage 1 analysis output in Redis when available."""
    return await redis_set(key, data, ttl_seconds=ttl_seconds)


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
