"""
services/biometric_service.py  —  Biometric Service (SaaS Orchestrator)

Single entry point for the biometric pipeline in a multi-tenant environment.
Callers (API endpoints, background workers) interact only with this class;
they never touch CNN1D or Stage 1 directly.

Responsibilities
────────────────
1. Load or create the per-(site_id, user_id) UserProfile.
2. Run CNN1D.extract() to obtain a fixed-length embedding.
3. Compute cosine distance between the new embedding and the stored centroid
   (if one exists).
4. Determine whether the user is still in the learning phase.
5. Build a ContextualBiometricInput and hand it to stage1_biometric.run().
6. Update the profile (centroid, sample counts) based on the Stage 1 verdict.
7. Return the BiometricResult to the caller.

Threading / async
─────────────────
BiometricService is designed to be instantiated once (as a singleton or DI
component) and used from multiple threads.  The profile store handles its own
locking.  CNN1D inference is CPU-bound and GIL-held; for async FastAPI
endpoints, run evaluate() inside asyncio.to_thread().

Example (FastAPI)::

    service = BiometricService(
        cnn        = CNN1D(out_dim=32),
        store      = RedisProfileStore(redis_client),
    )

    @router.post("/biometric/evaluate")
    async def evaluate(body: EvaluateRequest):
        ctx     = BiometricContext(site_id=body.site_id, user_id=body.user_id)
        result  = await asyncio.to_thread(
            service.evaluate,
            raw_signal   = body.signal,
            theta        = body.theta,
            h_exp        = body.h_exp,
            server_load  = body.server_load,
            context      = ctx,
        )
        return result
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, List, Optional

from ..models.cnn1d import CNN1D
from ..models.stage1_biometric import (
    analyze_biometrics,
    build_behavioral_baseline,
    calculate_behavioral_risk,
    prepare_stage2_input,
    run as stage1_run,
    typing_pattern_hash,
)
from ..pipeline.contracts import (
    BiometricContext,
    BiometricResult,
    ContextualBiometricInput,
    HoneypotVerdict,
    LEARNING_PHASE_MIN_SAMPLES,
    UserProfile,
)
from .biometric_profile_store import AbstractProfileStore, InMemoryProfileStore
from .redis_client import redis_del, redis_get, redis_set

logger = logging.getLogger("entropy_prime.biometric_service")

PROFILE_CACHE_TTL_SECONDS = 60 * 60 * 24
BASELINE_MIN_SAMPLES = 30

_MEM_PROFILES: dict[str, dict[str, Any]] = {}
_MEM_BASELINES: dict[str, dict[str, Any]] = {}
_MEM_HISTORY: dict[str, list[dict[str, Any]]] = {}
_MEM_ANOMALIES: dict[str, list[dict[str, Any]]] = {}
_MEM_FEEDBACK: list[dict[str, Any]] = []


class BiometricService:
    """
    Stateless orchestrator; all mutable state lives in the injected store.

    Parameters
    ──────────
    cnn         — a CNN1D instance (shared, thread-safe under no_grad).
    store       — an AbstractProfileStore implementation.
    out_dim     — embedding dimension; must match cnn.out_dim.
    """

    def __init__(
        self,
        cnn:   Optional[CNN1D]               = None,
        store: Optional[AbstractProfileStore] = None,
        out_dim: int = 32,
    ) -> None:
        self._cnn   = cnn   or CNN1D(out_dim=out_dim)
        self._store = store or InMemoryProfileStore()
        self._out_dim = self._cnn.out_dim

    # ── Public API ─────────────────────────────────────────────────────────────

    def evaluate(
        self,
        *,
        raw_signal:  List[float],
        theta:       float,
        h_exp:       float,
        context:     BiometricContext,
        server_load: float = 0.0,
        latent_vector: Optional[List[float]] = None,
    ) -> BiometricResult:
        """
        Full pipeline: signal → embedding → profile lookup → Stage 1 → profile update.

        Parameters
        ──────────
        raw_signal    — variable-length keystroke / touch / accel trace.
        theta         — humanity score computed upstream (0–1).
        h_exp         — entropy value from the encoder.
        context       — (site_id, user_id) pair.
        server_load   — passed through to downstream stages unchanged.
        latent_vector — optional pre-computed latent from the autoencoder.

        Returns
        ───────
        BiometricResult — verdict + confidence + centroid_dist + context.
        """
        # 1. Extract embedding
        embedding: List[float] = self._cnn.extract(raw_signal)

        # 2. Load (or create) the per-site user profile
        profile, is_new = self._store.get_or_create(context.site_id, context.user_id)
        if is_new:
            logger.info(
                "[Service] New user profile created: site=%r user=%r",
                context.site_id, context.user_id,
            )

        # 3. Validate / set embedding dim on first sample
        if profile.embedding_dim is None:
            profile.embedding_dim = len(embedding)
        elif profile.embedding_dim != len(embedding):
            logger.error(
                "[Service] Embedding dim mismatch: stored=%d got=%d — skipping centroid update",
                profile.embedding_dim, len(embedding),
            )
            embedding = embedding[:profile.embedding_dim]  # truncate to stored dim

        # 4. Compute cosine distance to stored centroid (None if not yet available)
        cdist: Optional[float] = (
            _cosine_distance(embedding, profile.centroid)
            if profile.centroid is not None
            else None
        )

        # 5. Build ContextualBiometricInput for Stage 1
        inp = ContextualBiometricInput(
            theta         = theta,
            h_exp         = h_exp,
            server_load   = server_load,
            latent_vector = latent_vector or [],
            context       = context,
            learning_phase= profile.in_learning_phase,
            centroid_dist = cdist,
        )

        # 6. Run Stage 1
        result = stage1_run(inp)

        # 7. Update profile based on verdict
        self._update_profile(profile, embedding, result)

        logger.debug(
            "[Service] site=%r user=%r verdict=%s conf=%s learning=%s cdist=%s",
            context.site_id, context.user_id,
            result.verdict, result.confidence,
            profile.in_learning_phase,
            f"{cdist:.3f}" if cdist is not None else "n/a",
        )

        return result

    def reset_profile(self, site_id: str, user_id: str) -> bool:
        """
        Delete a user's stored profile (e.g. on explicit user request or GDPR erasure).
        Returns True if a profile existed and was removed.
        """
        removed = self._store.delete(site_id, user_id)
        if removed:
            logger.info("[Service] Profile deleted: site=%r user=%r", site_id, user_id)
        return removed

    def get_profile(self, site_id: str, user_id: str) -> Optional[UserProfile]:
        """Read-only access to a stored profile (admin / debug endpoints)."""
        return self._store.get(site_id, user_id)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _update_profile(
        self,
        profile:   UserProfile,
        embedding: List[float],
        result:    BiometricResult,
    ) -> None:
        """
        Update centroid and counters, then persist.

        Centroid update strategy
        ────────────────────────
        We maintain a running mean of confirmed-HUMAN embeddings using an
        exponential moving average (EMA) once the learning phase is complete,
        and a simple cumulative mean during the learning phase.  This keeps
        the centroid representative without storing all historical embeddings.

        HUMAN verdicts update the centroid. During LEARNING we also treat
        high-theta samples as human evidence so profiles can graduate.
        BOT / SUSPECT samples increment sample_count only.
        """
        profile.sample_count += 1

        is_learning_human = (
            result.verdict == HoneypotVerdict.LEARNING
            and float(result.theta) >= 0.30
        )
        if result.verdict == HoneypotVerdict.HUMAN or is_learning_human:
            profile.human_count += 1
            profile.centroid = _update_centroid(
                old_centroid  = profile.centroid,
                new_embedding = embedding,
                human_count   = profile.human_count,
            )

        self._store.save(profile)


# ── Math utilities ─────────────────────────────────────────────────────────────

def _cosine_distance(a: List[float], b: List[float]) -> float:
    """
    Cosine distance in [0, 1]:  0 = identical direction, 1 = orthogonal / opposite.

    Returns 1.0 on zero-vector edge cases so they never receive a centroid boost.
    """
    if len(a) != len(b):
        return 1.0

    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))

    if mag_a < 1e-9 or mag_b < 1e-9:
        return 1.0

    cosine_sim = dot / (mag_a * mag_b)
    # Clamp to [-1, 1] to guard against floating-point overshoot
    cosine_sim = max(-1.0, min(1.0, cosine_sim))
    return (1.0 - cosine_sim) / 2.0


def _update_centroid(
    old_centroid:  Optional[List[float]],
    new_embedding: List[float],
    human_count:   int,
    ema_alpha:     float = 0.05,
) -> List[float]:
    """
    Update the running centroid with the new human embedding.

    • During learning phase (human_count ≤ LEARNING_PHASE_MIN_SAMPLES):
        cumulative mean — each sample has equal weight.
    • After graduation:
        EMA with ema_alpha — recent samples matter more, handles drift.

    ema_alpha=0.05 means ~20-sample effective window.
    """
    if old_centroid is None:
        # First human sample — centroid IS the embedding
        return list(new_embedding)

    dim = len(new_embedding)

    if human_count <= LEARNING_PHASE_MIN_SAMPLES:
        # Cumulative mean: c_n = c_{n-1} + (x_n - c_{n-1}) / n
        alpha = 1.0 / human_count
    else:
        alpha = ema_alpha

    return [
        (1.0 - alpha) * c + alpha * e
        for c, e in zip(old_centroid, new_embedding)
    ]


# ── PARIK Stage 1 behavioral feature/profile service ──────────────────────

def extract_biometric_features(raw_event: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a raw browser/user-interaction event into Stage 1 features.

    The extractor accepts both snake_case API fields and camelCase browser
    telemetry fields so frontend collectors can evolve independently.
    """
    event = dict(raw_event or {})
    timestamp = _parse_timestamp(event.get("timestamp")) or datetime.now(timezone.utc)
    key_intervals = _number_list(
        event.get("key_intervals")
        or event.get("keystroke_intervals")
        or event.get("interKeyDelays")
        or []
    )

    keystroke_speed = _float(
        event.get("keystroke_speed"),
        _chars_per_minute(event.get("text_length") or event.get("char_count"), event.get("typing_duration_ms")),
    )
    error_rate = _float(
        event.get("error_rate"),
        _safe_ratio(event.get("corrections") or event.get("backspaces"), event.get("text_length") or event.get("char_count"), 100.0),
    )
    key_dwell_time = _float(event.get("key_dwell_time") or event.get("avgDwell"))
    inter_key_delay = _float(
        event.get("inter_key_delay") or event.get("avgFlight"),
        sum(key_intervals) / len(key_intervals) if key_intervals else 0.0,
    )
    keystroke_consistency = (
        _pstdev(key_intervals) / max(sum(key_intervals) / len(key_intervals), 1.0)
        if len(key_intervals) > 1 else 0.0
    )

    os_name = str(event.get("os") or event.get("platform") or "")
    browser = str(event.get("browser") or event.get("user_agent") or "")
    resolution = str(event.get("screen_resolution") or event.get("resolution") or "")
    device_id = str(event.get("device_id") or event.get("deviceId") or "")
    device_fingerprint = event.get("device_fingerprint") or _fingerprint(
        "|".join([device_id, os_name, browser, resolution])
    )

    features = {
        "user_id": str(event.get("user_id") or event.get("userId") or ""),
        "timestamp": timestamp.isoformat(),
        "keystroke_speed": keystroke_speed,
        "error_rate": error_rate,
        "key_dwell_time": key_dwell_time,
        "inter_key_delay": inter_key_delay,
        "keystroke_consistency": keystroke_consistency,
        "typing_pattern_hash": event.get("typing_pattern_hash") or typing_pattern_hash(key_intervals),
        "mouse_velocity": _float(event.get("mouse_velocity") or event.get("mouse_speed") or event.get("avgSpeed")),
        "mouse_acceleration": _float(event.get("mouse_acceleration") or event.get("avgAccel")),
        "click_interval": _float(event.get("click_interval") or event.get("avgClickInterval")),
        "scroll_speed": _float(event.get("scroll_speed") or event.get("avgScrollSpeed")),
        "device_id": device_id or str(device_fingerprint),
        "device_fingerprint": str(device_fingerprint),
        "os": os_name,
        "browser": browser,
        "screen_resolution": resolution,
        "ip_address": str(event.get("ip_address") or event.get("ip") or ""),
        "location": event.get("location") or event.get("country") or "",
        "hour_of_day": timestamp.hour,
        "day_of_week": timestamp.weekday(),
        "is_weekend": timestamp.weekday() >= 5,
        "is_business_hours": timestamp.weekday() < 5 and 9 <= timestamp.hour < 17,
        "activity_frequency": _float(event.get("activity_frequency") or event.get("actions_per_hour")),
        "session_duration": _float(event.get("session_duration") or event.get("session_duration_seconds")),
        "unique_ip_count": _float(event.get("unique_ip_count"), 1.0 if event.get("ip_address") or event.get("ip") else 0.0),
        "device_change_frequency": _float(event.get("device_change_frequency")),
        "user_role": event.get("user_role") or event.get("role") or "user",
        "department": event.get("department") or "",
        "data_classification": event.get("data_classification") or "",
        "resource_sensitivity": _resource_sensitivity(event),
        "peer_group": event.get("peer_group") or event.get("department") or "",
    }
    return features


async def save_user_profile(
    user_id: str,
    profile_data: dict[str, Any],
    db: Any = None,
) -> str:
    """Create/update the Stage 1 profile document and cache it in Redis."""
    profile_id = str(profile_data.get("profile_id") or profile_data.get("_id") or uuid.uuid4())
    now = _utc_iso()
    doc = {
        **dict(profile_data),
        "profile_id": profile_id,
        "user_id": user_id,
        "updated_at": now,
    }
    doc.setdefault("created_at", now)
    doc.setdefault("profile_version", 1)

    if db is not None:
        await db.user_profiles.update_one(
            {"user_id": user_id},
            {"$set": doc},
            upsert=True,
        )
    else:
        old_version = int(_MEM_PROFILES.get(user_id, {}).get("profile_version", 0))
        doc["profile_version"] = max(int(doc.get("profile_version", 1)), old_version + 1)
        _MEM_PROFILES[user_id] = doc

    await redis_set(_profile_cache_key(user_id), doc, ttl_seconds=PROFILE_CACHE_TTL_SECONDS)
    return profile_id


async def load_user_profile(user_id: str, db: Any = None) -> Optional[dict[str, Any]]:
    """Load a Stage 1 profile from Redis, MongoDB, or in-memory fallback."""
    cached = await redis_get(_profile_cache_key(user_id))
    if cached:
        try:
            data = json.loads(cached)
            data["cached"] = True
            return data
        except json.JSONDecodeError:
            await redis_del(_profile_cache_key(user_id))

    if db is not None:
        doc = await db.user_profiles.find_one({"user_id": user_id})
        if doc:
            data = _clean_doc(doc)
            data["cached"] = False
            await redis_set(_profile_cache_key(user_id), data, ttl_seconds=PROFILE_CACHE_TTL_SECONDS)
            return data
        return None

    doc = _MEM_PROFILES.get(user_id)
    if not doc:
        return None
    return {**doc, "cached": False}


async def create_baseline(
    user_id: str,
    training_data_30_days: Iterable[dict[str, Any]],
    db: Any = None,
) -> dict[str, Any]:
    """Create a baseline from roughly 30 days of behavioral samples."""
    features = [
        row if "keystroke_speed" in row or "hour_of_day" in row else extract_biometric_features(row)
        for row in training_data_30_days
    ]
    baseline = build_behavioral_baseline(features, user_id=user_id, min_samples=BASELINE_MIN_SAMPLES)
    await _save_baseline(user_id, baseline, db=db)
    return baseline


async def update_user_baseline(
    user_id: str,
    new_data: dict[str, Any],
    db: Any = None,
) -> dict[str, Any]:
    """Append a sample to history and rebuild a bounded rolling baseline."""
    sample = new_data if "keystroke_speed" in new_data else extract_biometric_features(new_data)
    await _append_history(user_id, sample, db=db)
    history = await get_profile_history(user_id, limit=500, db=db)
    existing = await get_baseline(user_id, db=db)
    if existing and existing.get("baseline_ready") and len(history) < BASELINE_MIN_SAMPLES:
        baseline = _merge_baseline_sample(existing, sample)
    else:
        baseline = build_behavioral_baseline(history, user_id=user_id, min_samples=BASELINE_MIN_SAMPLES)
    await _save_baseline(user_id, baseline, db=db)
    return baseline


async def update_baseline(user_id: str, new_sample: dict[str, Any], db: Any = None) -> dict[str, Any]:
    """Alias from the Stage 1 spec."""
    return await update_user_baseline(user_id, new_sample, db=db)


async def get_baseline(user_id: str, db: Any = None) -> Optional[dict[str, Any]]:
    """Load baseline stats from Redis, MongoDB, or in-memory fallback."""
    cached = await redis_get(_baseline_cache_key(user_id))
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            await redis_del(_baseline_cache_key(user_id))

    if db is not None:
        doc = await db.baselines.find_one({"user_id": user_id})
        if doc:
            baseline = _clean_doc(doc)
            await redis_set(_baseline_cache_key(user_id), baseline, ttl_seconds=PROFILE_CACHE_TTL_SECONDS)
            return baseline
        return None
    return _MEM_BASELINES.get(user_id)


async def baseline_ready(user_id: str, db: Any = None) -> bool:
    """True when Stage 1 has enough history to run anomaly detection."""
    baseline = await get_baseline(user_id, db=db)
    return bool(baseline and baseline.get("baseline_ready"))


async def get_profile_history(
    user_id: str,
    limit: int = 100,
    db: Any = None,
) -> list[dict[str, Any]]:
    """Return recent behavioral feature samples for a user."""
    limit = max(1, min(int(limit), 1000))
    if db is not None:
        cursor = db.biometric_history.find({"user_id": user_id}).sort("timestamp", -1).limit(limit)
        rows = [_clean_doc(row) async for row in cursor]
        return list(reversed(rows))
    return list(_MEM_HISTORY.get(user_id, [])[-limit:])


async def log_anomaly(
    user_id: str,
    analysis: dict[str, Any],
    risk: dict[str, Any],
    db: Any = None,
) -> None:
    """Persist an anomaly event when Stage 1 flags one."""
    doc = {
        "anomaly_id": str(uuid.uuid4()),
        "user_id": user_id,
        "timestamp": _utc_iso(),
        "anomaly_score": analysis.get("anomaly_score", 0.0),
        "confidence": analysis.get("confidence", 0.0),
        "anomaly_flags": analysis.get("anomaly_flags", []),
        "component_scores": analysis.get("component_scores", {}),
        "risk_score": risk.get("risk_score", 0.0),
        "risk_level": risk.get("risk_level", "low"),
        "trend": risk.get("trend", "stable"),
    }
    if db is not None:
        await db.anomaly_logs.insert_one(doc)
    else:
        _MEM_ANOMALIES.setdefault(user_id, []).append(doc)


async def get_anomaly_history(
    user_id: str,
    limit: int = 100,
    db: Any = None,
) -> list[dict[str, Any]]:
    """Return recent anomaly events for a user."""
    limit = max(1, min(int(limit), 1000))
    if db is not None:
        cursor = db.anomaly_logs.find({"user_id": user_id}).sort("timestamp", -1).limit(limit)
        return [_clean_doc(row) async for row in cursor]
    return list(reversed(_MEM_ANOMALIES.get(user_id, [])[-limit:]))


async def record_feedback(
    user_id: str,
    feedback: str,
    *,
    source: str = "user",
    analysis_id: str = "",
    db: Any = None,
) -> dict[str, Any]:
    """Store user/admin feedback for future adaptive learning."""
    doc = {
        "feedback_id": str(uuid.uuid4()),
        "analysis_id": analysis_id,
        "user_id": user_id,
        "source": source,
        "feedback": feedback,
        "timestamp": _utc_iso(),
    }
    if db is not None:
        await db.stage1_feedback.insert_one(doc)
    else:
        _MEM_FEEDBACK.append(doc)
    return doc


async def analyze_user_event(
    user_id: str,
    raw_event: dict[str, Any],
    db: Any = None,
) -> dict[str, Any]:
    """
    End-to-end Stage 1 event analysis for API or pipeline callers.

    It extracts features, loads/updates profile state, scores anomalies, logs
    flagged events, and emits Stage 2-ready payload data.
    """
    features = extract_biometric_features({**dict(raw_event or {}), "user_id": user_id})
    profile = await load_user_profile(user_id, db=db)
    if profile is None:
        profile = {
            "user_id": user_id,
            "profile": {},
            "baseline_days": 0,
            "baseline_ready": False,
            "last_activity": features["timestamp"],
            "profile_version": 0,
        }

    baseline = await get_baseline(user_id, db=db)
    history = await get_profile_history(user_id, limit=100, db=db)
    if baseline is None:
        baseline = build_behavioral_baseline(history + [features], user_id=user_id)

    if not baseline.get("baseline_ready"):
        analysis = {
            "user_id": user_id,
            "anomaly_score": 0.0,
            "confidence": 0.35,
            "anomaly_flags": ["baseline_building"],
            "component_scores": {name: 0.0 for name in ("keystroke", "mouse", "device", "timing", "location", "context")},
            "historical_baseline": baseline,
            "isolation_forest_score": None,
            "trend": "stable",
            "is_anomalous": False,
        }
    else:
        analysis = analyze_biometrics(features, baseline, history=history)

    risk = calculate_behavioral_risk(analysis)
    await update_user_baseline(user_id, features, db=db)
    updated_baseline = await get_baseline(user_id, db=db) or baseline

    profile_doc = {
        **profile,
        "user_id": user_id,
        "profile": {
            **dict(profile.get("profile", {}) if isinstance(profile.get("profile"), dict) else {}),
            "last_features": features,
            "last_risk": risk,
        },
        "baseline_days": int(updated_baseline.get("baseline_days", 0) or 0),
        "baseline_ready": bool(updated_baseline.get("baseline_ready")),
        "last_activity": features["timestamp"],
    }
    await save_user_profile(user_id, profile_doc, db=db)

    if analysis.get("is_anomalous"):
        await log_anomaly(user_id, analysis, risk, db=db)

    return {
        "features": features,
        "profile": profile_doc,
        "baseline": updated_baseline,
        "analysis": analysis,
        "risk": risk,
        "stage2_input": prepare_stage2_input(analysis, risk, user_profile=profile_doc),
    }


async def dashboard_stats(db: Any = None) -> dict[str, Any]:
    """Aggregate high-level Stage 1 dashboard stats."""
    if db is not None:
        total_users = await db.user_profiles.count_documents({})
        ready_users = await db.baselines.count_documents({"baseline_ready": True})
        anomalies = await db.anomaly_logs.count_documents({})
        cursor = db.anomaly_logs.find({}).sort("timestamp", -1).limit(200)
        risks = [_float(row.get("risk_score")) async for row in cursor]
    else:
        total_users = len(_MEM_PROFILES)
        ready_users = sum(1 for b in _MEM_BASELINES.values() if b.get("baseline_ready"))
        anomalies = sum(len(v) for v in _MEM_ANOMALIES.values())
        risks = [_float(row.get("risk_score")) for rows in _MEM_ANOMALIES.values() for row in rows[-200:]]
    return {
        "total_users_profiled": total_users,
        "baseline_completion": round((ready_users / total_users) if total_users else 0.0, 4),
        "anomaly_count": anomalies,
        "average_biometric_score": round(sum(risks) / len(risks), 4) if risks else 0.0,
    }


async def dashboard_anomalies(limit: int = 100, db: Any = None) -> dict[str, Any]:
    """Recent anomaly feed plus simple flag heat-map."""
    if db is not None:
        cursor = db.anomaly_logs.find({}).sort("timestamp", -1).limit(limit)
        rows = [_clean_doc(row) async for row in cursor]
    else:
        rows = [row for values in _MEM_ANOMALIES.values() for row in values]
        rows = list(reversed(rows[-limit:]))
    heatmap: dict[str, int] = {}
    for row in rows:
        for flag in row.get("anomaly_flags", []) or []:
            heatmap[flag] = heatmap.get(flag, 0) + 1
    return {"anomalies": rows, "count": len(rows), "heatmap": heatmap}


async def user_risk(user_id: str, db: Any = None) -> dict[str, Any]:
    """Return the latest risk posture for a user."""
    profile = await load_user_profile(user_id, db=db) or {}
    history = await get_anomaly_history(user_id, limit=20, db=db)
    latest = history[0] if history else {}
    return {
        "user_id": user_id,
        "risk_score": _float(latest.get("risk_score"), _float(profile.get("profile", {}).get("last_risk", {}).get("risk_score"))),
        "risk_level": latest.get("risk_level") or profile.get("profile", {}).get("last_risk", {}).get("risk_level", "low"),
        "trend": latest.get("trend") or profile.get("profile", {}).get("last_risk", {}).get("trend", "stable"),
        "recent_anomalies": history,
    }


async def model_health(db: Any = None) -> dict[str, Any]:
    """Operational health summary for the Stage 1 behavioral model."""
    stats = await dashboard_stats(db=db)
    return {
        "model": "statistical_zscore_with_optional_isolation_forest",
        "model_loaded": True,
        "sklearn_available": _sklearn_available(),
        "last_retrain_date": None,
        "baseline_completion": stats["baseline_completion"],
        "target_latency_ms": 100,
        "status": "healthy",
    }


async def features_importance(user_id: Optional[str] = None, db: Any = None) -> dict[str, Any]:
    """Return feature importance values from one baseline or all baselines."""
    if user_id:
        baseline = await get_baseline(user_id, db=db) or {}
        return {"user_id": user_id, "feature_importance": baseline.get("feature_importance", {})}
    if db is not None:
        cursor = db.baselines.find({}).limit(500)
        baselines = [_clean_doc(row) async for row in cursor]
    else:
        baselines = list(_MEM_BASELINES.values())
    totals: dict[str, float] = {}
    for baseline in baselines:
        for name, value in (baseline.get("feature_importance", {}) or {}).items():
            totals[name] = totals.get(name, 0.0) + _float(value)
    count = max(len(baselines), 1)
    return {"feature_importance": {name: round(value / count, 4) for name, value in totals.items()}}


async def _save_baseline(user_id: str, baseline: dict[str, Any], db: Any = None) -> None:
    baseline = {**baseline, "user_id": user_id, "updated_at": _utc_iso()}
    if db is not None:
        await db.baselines.update_one({"user_id": user_id}, {"$set": baseline}, upsert=True)
    else:
        _MEM_BASELINES[user_id] = baseline
    await redis_set(_baseline_cache_key(user_id), baseline, ttl_seconds=PROFILE_CACHE_TTL_SECONDS)


async def _append_history(user_id: str, sample: dict[str, Any], db: Any = None) -> None:
    doc = {**sample, "history_id": str(uuid.uuid4()), "user_id": user_id}
    if db is not None:
        await db.biometric_history.insert_one(doc)
    else:
        _MEM_HISTORY.setdefault(user_id, []).append(doc)
        _MEM_HISTORY[user_id] = _MEM_HISTORY[user_id][-1000:]


def _merge_baseline_sample(baseline: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    updated = {**baseline, "updated_at": _utc_iso()}
    sample_count = int(_float(updated.get("sample_count"), 0.0)) + 1
    updated["sample_count"] = sample_count
    updated["baseline_ready"] = True

    feature_stats = {
        name: dict(stats)
        for name, stats in (updated.get("feature_stats", {}) or {}).items()
    }
    for name, stats in feature_stats.items():
        if sample.get(name) is None:
            continue
        value = _float(sample.get(name))
        old_mean = _float(stats.get("mean"))
        old_std = max(_float(stats.get("std"), 1.0), 1e-6)
        alpha = 1.0 / max(sample_count, 1)
        stats["mean"] = (1.0 - alpha) * old_mean + alpha * value
        stats["std"] = max((1.0 - alpha) * old_std + alpha * abs(value - old_mean), 1e-6)
        stats["min"] = min(_float(stats.get("min"), value), value)
        stats["max"] = max(_float(stats.get("max"), value), value)

    selected = list(updated.get("selected_features", []) or feature_stats.keys())
    vector = [_float(sample.get(name), feature_stats.get(name, {}).get("mean", 0.0)) for name in selected]
    vectors = list(updated.get("feature_vectors", []) or [])
    vectors.append(vector)
    updated["feature_vectors"] = vectors[-500:]
    updated["feature_stats"] = feature_stats

    device = str(sample.get("device_id") or sample.get("device_fingerprint") or "")
    if device:
        updated["known_devices"] = sorted(set(updated.get("known_devices", []) or []) | {device})
    ip_address = str(sample.get("ip_address") or "")
    if ip_address:
        updated["known_ip_addresses"] = sorted(set(updated.get("known_ip_addresses", []) or []) | {ip_address})
    hour = int(_float(sample.get("hour_of_day"), -1))
    if 0 <= hour <= 23:
        updated["normal_hours"] = sorted(set(updated.get("normal_hours", []) or []) | {hour})

    updated["feature_importance"] = _feature_importance_from_stats(feature_stats)
    return updated


def _profile_cache_key(user_id: str) -> str:
    return f"stage1:profile:{user_id}"


def _baseline_cache_key(user_id: str) -> str:
    return f"stage1:baseline:{user_id}"


def _resource_sensitivity(event: dict[str, Any]) -> float:
    if event.get("resource_sensitivity") is not None:
        return _float(event.get("resource_sensitivity"))
    classification = str(event.get("data_classification") or "").lower()
    if classification in {"restricted", "secret", "critical"}:
        return 0.9
    if classification in {"confidential", "sensitive"}:
        return 0.7
    return 0.2 if classification else 0.0


def _chars_per_minute(chars: Any, duration_ms: Any) -> float:
    duration = _float(duration_ms)
    if duration <= 0:
        return 0.0
    return _float(chars) / (duration / 60000.0)


def _safe_ratio(numerator: Any, denominator: Any, multiplier: float = 1.0) -> float:
    den = _float(denominator)
    if den <= 0:
        return 0.0
    return (_float(numerator) / den) * multiplier


def _number_list(values: Iterable[Any]) -> list[float]:
    if not isinstance(values, Iterable) or isinstance(values, (str, bytes, dict)):
        return []
    return [_float(value) for value in values]


def _pstdev(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    avg = sum(values) / len(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / len(values))


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _feature_importance_from_stats(feature_stats: dict[str, dict[str, float]]) -> dict[str, float]:
    spreads = {
        name: max(_float(stats.get("std")), 1e-6)
        for name, stats in feature_stats.items()
    }
    total = sum(spreads.values()) or 1.0
    return {name: round(value / total, 4) for name, value in spreads.items()}


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _clean_doc(doc: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(doc)
    if "_id" in cleaned:
        cleaned["_id"] = str(cleaned["_id"])
    for key, value in list(cleaned.items()):
        if isinstance(value, datetime):
            cleaned[key] = value.isoformat()
    return cleaned


def _sklearn_available() -> bool:
    try:
        import sklearn  # noqa: F401
        return True
    except Exception:
        return False
